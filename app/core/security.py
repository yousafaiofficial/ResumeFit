import datetime as dt
import hashlib
import hmac
import logging
import secrets
from urllib.parse import urlsplit

import bcrypt
from fastapi import Cookie, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.session import UserSession
from app.models.user import User

logger = logging.getLogger("resumefit.security")
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except (ValueError, TypeError):
        return False


def hash_secret_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def generate_pre_auth_csrf_token() -> str:
    nonce = secrets.token_urlsafe(32)
    issued_at = str(int(_utcnow().timestamp()))
    message = f"preauth:{nonce}:{issued_at}".encode()
    signature = hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()
    return f"{nonce}.{issued_at}.{signature}"


def verify_pre_auth_csrf_token(token: str) -> bool:
    try:
        nonce, issued_at, signature = token.split(".", 2)
        issued_timestamp = int(issued_at)
    except (AttributeError, ValueError):
        return False

    now = int(_utcnow().timestamp())
    if issued_timestamp > now or now - issued_timestamp > settings.PREAUTH_CSRF_EXPIRE_SECONDS:
        return False

    message = f"preauth:{nonce}:{issued_at}".encode()
    expected = hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def require_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin is None:
        referer = request.headers.get("referer")
        if referer:
            parsed = urlsplit(referer)
            origin = (
                f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else None
            )

    allowed = {configured.rstrip("/") for configured in settings.ALLOWED_ORIGINS}
    if origin is None or origin.rstrip("/") not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request origin is not allowed.",
        )


def require_pre_auth_csrf(
    request: Request,
    csrf_header: str | None,
    pre_auth_cookie: str | None,
) -> None:
    require_same_origin(request)
    if (
        not csrf_header
        or not pre_auth_cookie
        or not hmac.compare_digest(csrf_header, pre_auth_cookie)
        or not verify_pre_auth_csrf_token(pre_auth_cookie)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token validation failed. Refresh the page and try again.",
        )


def create_user_session(db: Session, user: User) -> tuple[UserSession, str, str]:
    now = _utcnow()
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    user_session = UserSession(
        user_id=user.id,
        token_hash=hash_secret_token(session_token),
        csrf_token_hash=hash_secret_token(csrf_token),
        created_at=now,
        expires_at=now + dt.timedelta(days=settings.SESSION_EXPIRE_DAYS),
    )
    db.add(user_session)
    db.commit()
    db.refresh(user_session)
    return user_session, session_token, csrf_token


def set_session_cookie(response: Response, session_token: str, max_age: int) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.secure_cookies,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )


def set_pre_auth_csrf_cookie(response: Response, csrf_token: str) -> None:
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        max_age=settings.PREAUTH_CSRF_EXPIRE_SECONDS,
        httponly=True,
        secure=settings.secure_cookies,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=settings.secure_cookies,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path="/",
        secure=settings.secure_cookies,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )


def get_current_session(
    request: Request,
    session_cookie: str | None = Cookie(None, alias=settings.session_cookie_name),
    csrf_header: str | None = Header(None, alias="X-CSRF-Token"),
    db: Session = Depends(get_db),
) -> UserSession:
    if not session_cookie:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to continue.",
        )

    user_session = (
        db.query(UserSession)
        .filter(
            UserSession.token_hash == hash_secret_token(session_cookie),
            UserSession.revoked_at.is_(None),
        )
        .first()
    )
    if user_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired. Please sign in again.",
        )

    now = _utcnow()
    expires_at = user_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=dt.UTC)
    if expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired. Please sign in again.",
        )

    if request.method not in SAFE_METHODS:
        require_same_origin(request)
        if not csrf_header or not hmac.compare_digest(
            hash_secret_token(csrf_header), user_session.csrf_token_hash
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token validation failed. Refresh the page and try again.",
            )
    return user_session


def get_current_user(
    user_session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> User:
    user = db.get(User, user_session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not found or inactive.",
        )
    return user
