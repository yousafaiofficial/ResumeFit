"""Optional Google OAuth and single-use password recovery; no provider tokens persist."""

import base64
import datetime as dt
import hashlib
import hmac
import logging
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.core.security import (
    clear_auth_cookies,
    create_user_session,
    hash_password,
    hash_secret_token,
    require_pre_auth_csrf,
    set_session_cookie,
)
from app.models.recovery import AuthChallenge, GoogleIdentity
from app.models.session import UserSession
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logging.getLogger("resumefit.auth")
GENERIC_RESET = "If an eligible account exists, a reset link will be emailed shortly."


def google_enabled() -> bool:
    return bool(
        settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET and settings.PUBLIC_BASE_URL
    )


def recovery_enabled() -> bool:
    return bool(settings.RESEND_API_KEY and settings.EMAIL_FROM and settings.PUBLIC_BASE_URL)


def flow_cookie() -> str:
    return "__Host-resumefit_google" if settings.secure_cookies else "resumefit_google"


@router.get("/options")
def options():
    return {"google": google_enabled(), "password_reset": recovery_enabled()}


@router.get("/google/start")
@limiter.limit("5/minute")
def google_start(request: Request, db: Session = Depends(get_db)):
    if not google_enabled():
        raise HTTPException(503, "Google sign-in is not configured.")
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    db.query(AuthChallenge).filter(AuthChallenge.expires_at < dt.datetime.now(dt.UTC)).delete()
    db.add(
        AuthChallenge(
            token_hash=hash_secret_token(state),
            purpose="google",
            verifier=verifier,
            expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=10),
        )
    )
    db.commit()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": f"{settings.PUBLIC_BASE_URL}/api/v1/auth/google/callback",
        "response_type": "code",
        "scope": "openid email",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    response = RedirectResponse(
        "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params), 303
    )
    response.set_cookie(
        flow_cookie(),
        state,
        max_age=600,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def exchange_google(code: str, verifier: str) -> dict:
    # The access token comes only from Google's authenticated, server-side code
    # exchange. Use its fixed HTTPS UserInfo endpoint; never trust browser claims.
    with httpx.Client(timeout=15) as client:
        token_response = client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "code_verifier": verifier,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "redirect_uri": f"{settings.PUBLIC_BASE_URL}/api/v1/auth/google/callback",
            },
        )
        token_response.raise_for_status()
        token = token_response.json()["access_token"]
        profile = client.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {token}"},
        )
        profile.raise_for_status()
        return profile.json()


@router.get("/google/callback")
@limiter.limit("10/minute")
def google_callback(
    request: Request,
    state: str = "",
    code: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    response = RedirectResponse("/?auth_error=google", 303)
    response.delete_cookie(
        flow_cookie(), path="/", secure=settings.secure_cookies, httponly=True, samesite="lax"
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    cookie = request.cookies.get(flow_cookie(), "")
    if not google_enabled() or not state or not cookie or not hmac.compare_digest(state, cookie):
        return response
    challenge = db.get(AuthChallenge, hash_secret_token(state))
    if challenge is None or challenge.purpose != "google":
        return response
    verifier = challenge.verifier
    consumed = (
        db.query(AuthChallenge)
        .filter(
            AuthChallenge.token_hash == hash_secret_token(state),
            AuthChallenge.expires_at > dt.datetime.now(dt.UTC),
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    if not consumed or not verifier or error or not code:
        return response
    try:
        profile = exchange_google(code, verifier)
        subject, email = profile.get("sub"), profile.get("email")
        if (
            not isinstance(subject, str)
            or not subject
            or len(subject) > 255
            or not isinstance(email, str)
            or len(email) > 255
            or "@" not in email
            or profile.get("email_verified") is not True
        ):
            return response
        identity = db.get(GoogleIdentity, subject)
        user = db.get(User, identity.user_id) if identity else None
        if identity is None:
            # Never silently link an email/password account by matching email.
            if db.query(User).filter_by(email=email.strip().lower()).first():
                response.headers["location"] = "/?auth_error=existing_account"
                return response
            user = User(
                email=email.strip().lower(), password_hash=hash_password(secrets.token_urlsafe(48))
            )
            db.add(user)
            db.flush()
            db.add(GoogleIdentity(subject=subject, user_id=user.id))
            db.commit()
        if user is None or not user.is_active:
            return response
        session, token, _ = create_user_session(db, user)
        set_session_cookie(
            response, token, int((session.expires_at - session.created_at).total_seconds())
        )
        response.headers["location"] = "/"
    except (httpx.HTTPError, KeyError, ValueError, IntegrityError):
        db.rollback()
        # Never log authorization codes, access tokens, or provider response bodies.
        logger.warning("Google sign-in could not be completed.")
    return response


class ResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class ResetConfirm(BaseModel):
    token: str = Field(min_length=20, max_length=128)
    password: str = Field(min_length=10, max_length=72)


def send_reset_email(email: str, token: str) -> None:
    # Fragment tokens are not sent to HTTP servers or included in Referer headers.
    link = f"{settings.PUBLIC_BASE_URL}/#reset={token}"
    with httpx.Client(timeout=15) as client:
        result = client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json={
                "from": settings.EMAIL_FROM,
                "to": [email],
                "subject": "Reset your ResumeFit password",
                "text": f"Reset your password within 20 minutes: {link}\n\nIf you did not request this, ignore this email.",
            },
        )
        result.raise_for_status()


def deliver_reset_email(email: str, token: str) -> None:
    try:
        send_reset_email(email, token)
    except httpx.HTTPError:
        logger.warning("Password reset email delivery failed.")


@router.post("/password/forgot")
@limiter.limit("3/hour")
def forgot_password(
    request: Request,
    payload: ResetRequest,
    background_tasks: BackgroundTasks,
    csrf_header: str | None = Header(None, alias="X-CSRF-Token"),
    csrf_cookie: str | None = Cookie(None, alias=settings.csrf_cookie_name),
    db: Session = Depends(get_db),
):
    require_pre_auth_csrf(request, csrf_header, csrf_cookie)
    if not recovery_enabled():
        raise HTTPException(503, "Password reset is not configured.")
    user = db.query(User).filter_by(email=payload.email.strip().lower(), is_active=True).first()
    if user:
        # Per-account throttle persists across serverless instances.
        recent = (
            db.query(AuthChallenge)
            .filter(
                AuthChallenge.user_id == user.id,
                AuthChallenge.purpose == "reset",
                AuthChallenge.expires_at > dt.datetime.now(dt.UTC) + dt.timedelta(minutes=15),
            )
            .first()
        )
        if not recent:
            token = secrets.token_urlsafe(32)
            record = AuthChallenge(
                token_hash=hash_secret_token(token),
                purpose="reset",
                user_id=user.id,
                expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=20),
            )
            db.add(record)
            db.commit()
            # Deliver after the generic response, without tying response latency
            # to provider delivery. Vercel awaits ASGI background work.
            background_tasks.add_task(deliver_reset_email, user.email, token)
    return {"message": GENERIC_RESET}


@router.post("/password/reset")
@limiter.limit("5/minute")
def reset_password(
    request: Request,
    payload: ResetConfirm,
    csrf_header: str | None = Header(None, alias="X-CSRF-Token"),
    csrf_cookie: str | None = Cookie(None, alias=settings.csrf_cookie_name),
    db: Session = Depends(get_db),
):
    require_pre_auth_csrf(request, csrf_header, csrf_cookie)
    if len(payload.password.encode()) > 72:
        raise HTTPException(422, "Password must be at most 72 UTF-8 bytes.")
    challenge = db.get(AuthChallenge, hash_secret_token(payload.token))
    if challenge is None or challenge.purpose != "reset":
        raise HTTPException(400, "Reset link is invalid or expired.")
    user = db.query(User).filter_by(id=challenge.user_id).with_for_update().first()
    consumed = (
        db.query(AuthChallenge)
        .filter(
            AuthChallenge.token_hash == hash_secret_token(payload.token),
            AuthChallenge.purpose == "reset",
            AuthChallenge.expires_at > dt.datetime.now(dt.UTC),
        )
        .delete(synchronize_session=False)
    )
    if not consumed or user is None or not user.is_active:
        db.rollback()
        raise HTTPException(400, "Reset link is invalid or expired.")
    user.password_hash = hash_password(payload.password)
    db.query(UserSession).filter_by(user_id=user.id).update({"revoked_at": dt.datetime.now(dt.UTC)})
    db.query(AuthChallenge).filter_by(user_id=user.id, purpose="reset").delete(
        synchronize_session=False
    )
    db.commit()
    response = JSONResponse({"message": "Password updated. Sign in with your new password."})
    clear_auth_cookies(response)
    return response
