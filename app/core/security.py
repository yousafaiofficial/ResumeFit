import datetime as dt
import secrets
from typing import Optional
import bcrypt
import jwt
from fastapi import Cookie, Depends, Header, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(pw: str) -> str:
    """Hash password using bcrypt."""
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    """Verify password against bcrypt hash."""
    try:
        return bcrypt.checkpw(pw.encode()[:72], hashed.encode())
    except (ValueError, TypeError):
        return False


def generate_csrf_token() -> str:
    """Generate cryptographically secure CSRF token."""
    return secrets.token_hex(32)


def make_access_token(user_id: int) -> str:
    """Generate JWT signed with current active key id (kid) for key rotation."""
    now = dt.datetime.now(dt.timezone.utc)
    exp = now + dt.timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    headers = {"kid": settings.JWT_ACTIVE_KID}
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": exp,
        "type": "access",
    }
    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
        headers=headers,
    )


def decode_access_token(token: str) -> int:
    """Decode JWT validating against active or previous signing secret."""
    try:
        unverified_header = jwt.get_unverified_header(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token format.",
        )

    kid = unverified_header.get("kid", settings.JWT_ACTIVE_KID)
    keys = settings.jwt_verification_keys

    # Try matching key by kid, fallback to active or previous secret
    signing_secret = keys.get(kid, settings.SECRET_KEY)

    try:
        data = jwt.decode(
            token,
            signing_secret,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return int(data["sub"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired. Please sign in again.",
        )
    except (jwt.PyJWTError, ValueError, KeyError):
        # In case kid was not matched, try previous secret if present
        if settings.PREVIOUS_SECRET_KEY and signing_secret != settings.PREVIOUS_SECRET_KEY:
            try:
                data = jwt.decode(
                    token,
                    settings.PREVIOUS_SECRET_KEY,
                    algorithms=[settings.JWT_ALGORITHM],
                )
                return int(data["sub"])
            except Exception:
                pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token. Please sign in again.",
        )


def set_auth_cookies(response: Response, token: str, csrf_token: str | None = None) -> None:
    """Set secure httpOnly session cookie and optional CSRF cookie."""
    max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=token,
        max_age=max_age,
        expires=max_age,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )
    if csrf_token:
        # CSRF cookie is readable by JS to echo back in header
        response.set_cookie(
            key=settings.CSRF_COOKIE_NAME,
            value=csrf_token,
            max_age=max_age,
            expires=max_age,
            httponly=False,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            path="/",
        )


def clear_auth_cookies(response: Response) -> None:
    """Clear session and CSRF cookies on logout."""
    response.delete_cookie(settings.COOKIE_NAME, path="/", samesite=settings.COOKIE_SAMESITE)
    response.delete_cookie(settings.CSRF_COOKIE_NAME, path="/", samesite=settings.COOKIE_SAMESITE)


def get_current_user(
    request: Request,
    bearer_creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    session_cookie: Optional[str] = Cookie(None, alias=settings.COOKIE_NAME),
    csrf_cookie: Optional[str] = Cookie(None, alias=settings.CSRF_COOKIE_NAME),
    csrf_header: Optional[str] = Header(None, alias="X-CSRF-Token"),
    db: Session = Depends(get_db),
):
    """
    Extracts current authenticated user from either:
    1. HttpOnly Cookie (with CSRF verification on unsafe methods)
    2. Bearer Authorization header (for automated API callers)
    """
    from app.models.user import User

    token = None
    using_cookie = False

    if session_cookie:
        token = session_cookie
        using_cookie = True
    elif bearer_creds:
        token = bearer_creds.credentials

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to continue.",
        )

    # CSRF check for state-changing requests using cookie authentication
    if using_cookie and request.method in ("POST", "PUT", "DELETE", "PATCH"):
        if not csrf_header or not csrf_cookie or csrf_header != csrf_cookie:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token validation failed. Refresh the page and try again.",
            )

    user_id = decode_access_token(token)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not found.",
        )
    return user
