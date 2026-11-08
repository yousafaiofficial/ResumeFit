from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.core.security import (
    clear_auth_cookies,
    generate_csrf_token,
    get_current_user,
    hash_password,
    make_access_token,
    set_auth_cookies,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import (
    CsrfResponse,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/csrf", response_model=CsrfResponse)
def get_csrf(response: Response):
    """Issues a fresh CSRF token and sets the corresponding cookie."""
    token = generate_csrf_token()
    # Set non-httpOnly cookie for frontend to echo back in header
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )
    return CsrfResponse(csrf_token=token)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.RATE_LIMIT_REGISTER)
def register(
    request: Request,
    payload: UserRegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    """Registers a new user, hashes password, sets auth cookie, and returns session token."""
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

    token = make_access_token(user.id)
    csrf_token = generate_csrf_token()
    set_auth_cookies(response, token, csrf_token)

    return TokenResponse(token=token, email=user.email, csrf_token=csrf_token)


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_LOGIN)
def login(
    request: Request,
    payload: UserLoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    """Validates credentials, issues JWT, and sets secure httpOnly cookie."""
    user = db.query(User).filter_by(email=payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect.",
        )

    token = make_access_token(user.id)
    csrf_token = generate_csrf_token()
    set_auth_cookies(response, token, csrf_token)

    return TokenResponse(token=token, email=user.email, csrf_token=csrf_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    """Clears authentication session and CSRF cookies."""
    clear_auth_cookies(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    """Returns details for currently authenticated user."""
    return user
