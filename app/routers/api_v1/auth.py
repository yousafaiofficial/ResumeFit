import datetime as dt
import hmac
import secrets

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.core.security import (
    clear_auth_cookies,
    create_user_session,
    generate_pre_auth_csrf_token,
    get_current_session,
    get_current_user,
    hash_password,
    hash_secret_token,
    require_pre_auth_csrf,
    require_same_origin,
    set_pre_auth_csrf_cookie,
    set_session_cookie,
    verify_password,
)
from app.models.session import UserSession
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    CsrfResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/csrf", response_model=CsrfResponse)
def get_csrf(response: Response):
    """Issues a short-lived CSRF token for login and registration."""
    token = generate_pre_auth_csrf_token()
    set_pre_auth_csrf_cookie(response, token)
    return CsrfResponse(csrf_token=token)


@router.get("/csrf/session", response_model=CsrfResponse)
def refresh_session_csrf(
    user_session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
):
    """Rotate a session's CSRF token after an authenticated page reload."""
    token = secrets.token_urlsafe(32)
    user_session.csrf_token_hash = hash_secret_token(token)
    db.commit()
    return CsrfResponse(csrf_token=token)


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.RATE_LIMIT_REGISTER)
def register(
    request: Request,
    payload: UserRegisterRequest,
    response: Response,
    csrf_header: str | None = Header(None, alias="X-CSRF-Token"),
    pre_auth_cookie: str | None = Cookie(None, alias=settings.csrf_cookie_name),
    db: Session = Depends(get_db),
):
    """Registers a user and creates an opaque, database-backed session."""
    require_pre_auth_csrf(request, csrf_header, pre_auth_cookie)
    existing = db.query(User).filter_by(email=payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    user_session, session_token, csrf_token = create_user_session(db, user)
    set_session_cookie(
        response,
        session_token,
        int((user_session.expires_at - user_session.created_at).total_seconds()),
    )
    clear_auth_cookies_pre_auth(response)

    return AuthResponse(email=user.email, csrf_token=csrf_token)


@router.post("/login", response_model=AuthResponse)
@limiter.limit(settings.RATE_LIMIT_LOGIN)
def login(
    request: Request,
    payload: UserLoginRequest,
    response: Response,
    csrf_header: str | None = Header(None, alias="X-CSRF-Token"),
    pre_auth_cookie: str | None = Cookie(None, alias=settings.csrf_cookie_name),
    db: Session = Depends(get_db),
):
    """Validates credentials and creates an opaque server-side session."""
    require_pre_auth_csrf(request, csrf_header, pre_auth_cookie)
    user = db.query(User).filter_by(email=payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect.",
        )

    user_session, session_token, csrf_token = create_user_session(db, user)
    set_session_cookie(
        response,
        session_token,
        int((user_session.expires_at - user_session.created_at).total_seconds()),
    )
    clear_auth_cookies_pre_auth(response)

    return AuthResponse(email=user.email, csrf_token=csrf_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def logout(
    request: Request,
    response: Response,
    session_cookie: str | None = Cookie(None, alias=settings.session_cookie_name),
    csrf_header: str | None = Header(None, alias="X-CSRF-Token"),
    db: Session = Depends(get_db),
):
    """Revokes the presented session and clears cookies, including expired sessions."""
    require_same_origin(request)
    if session_cookie:
        user_session = (
            db.query(UserSession)
            .filter(UserSession.token_hash == hash_secret_token(session_cookie))
            .first()
        )
        if user_session and user_session.revoked_at is None:
            now = dt.datetime.now(dt.UTC)
            expires_at = user_session.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=dt.UTC)
            if expires_at > now:
                if not csrf_header or not hmac.compare_digest(
                    hash_secret_token(csrf_header), user_session.csrf_token_hash
                ):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="CSRF token validation failed. Refresh the page and try again.",
                    )
            user_session.revoked_at = now
            db.commit()
    clear_auth_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    """Returns details for currently authenticated user."""
    return user


def clear_auth_cookies_pre_auth(response: Response) -> None:
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path="/",
        secure=settings.secure_cookies,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )
