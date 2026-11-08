import datetime as dt
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import Response
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.core.security import set_session_cookie
from app.models.session import UserSession


def _new_pre_auth_headers(client):
    response = client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    return {
        "Origin": "http://localhost:8000",
        "X-CSRF-Token": response.json()["csrf_token"],
    }


def _set_cookie_headers(response, name):
    headers = response.headers
    cookie_headers = (
        headers.get_list("set-cookie")
        if hasattr(headers, "get_list")
        else headers.getlist("set-cookie")
    )
    value = next(cookie for cookie in cookie_headers if cookie.startswith(name + "="))
    return value.lower()


def test_pre_auth_csrf_token_endpoint(client):
    res = client.get("/api/v1/auth/csrf")
    assert res.status_code == 200
    csrf_token = res.json()["csrf_token"]
    assert len(csrf_token) > 100
    cookie = _set_cookie_headers(res, settings.csrf_cookie_name)
    assert "httponly" in cookie
    assert "path=/" in cookie
    assert "samesite=lax" in cookie
    assert "max-age=600" in cookie
    csp = res.headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "style-src-attr 'none'" in csp
    assert "unsafe-inline" not in csp


def test_expired_pre_auth_csrf_token_is_rejected(client, monkeypatch):
    import app.core.security as security

    headers = _new_pre_auth_headers(client)
    original_now = security._utcnow()
    monkeypatch.setattr(
        security,
        "_utcnow",
        lambda: original_now + dt.timedelta(seconds=settings.PREAUTH_CSRF_EXPIRE_SECONDS + 1),
    )
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "missing@example.com",
            "password": "SecurePassword123!",  # pragma: allowlist secret
        },
        headers=headers,
    )
    assert response.status_code == 403


def test_register_enforces_password_length(client, pre_auth_headers):
    payload = {"email": "shortpw@example.com", "password": "short"}
    res = client.post("/api/v1/auth/register", json=payload, headers=pre_auth_headers)
    assert res.status_code == 422
    assert res.json()["code"] == "VALIDATION_ERROR"


def test_register_and_login_create_cookie_sessions(client, db_session):
    payload = {"email": "newuser@example.com", "password": "SuperSecurePassword123!"}
    register = client.post(
        "/api/v1/auth/register",
        json=payload,
        headers=_new_pre_auth_headers(client),
    )
    assert register.status_code == 201
    assert "token" not in register.json()
    assert register.json()["email"] == "newuser@example.com"
    assert register.json()["csrf_token"]
    assert register.cookies[settings.session_cookie_name] not in register.text

    session_cookie = _set_cookie_headers(register, settings.session_cookie_name)
    assert "httponly" in session_cookie
    assert "path=/" in session_cookie
    assert "samesite=lax" in session_cookie
    assert "max-age=604800" in session_cookie
    assert "secure" not in session_cookie

    user_session = db_session.query(UserSession).one()
    assert (
        hashlib.sha256(register.json()["csrf_token"].encode()).hexdigest()
        == user_session.csrf_token_hash
    )
    assert (
        hashlib.sha256(register.cookies[settings.session_cookie_name].encode()).hexdigest()
        == user_session.token_hash
    )
    assert register.cookies[settings.session_cookie_name] not in user_session.token_hash

    restored = client.get("/api/v1/auth/me")
    assert restored.status_code == 200
    assert restored.json()["email"] == payload["email"]

    previous_csrf = register.json()["csrf_token"]
    refreshed_csrf = client.get("/api/v1/auth/csrf/session")
    assert refreshed_csrf.status_code == 200
    assert refreshed_csrf.json()["csrf_token"] != previous_csrf

    login = client.post(
        "/api/v1/auth/login",
        json=payload,
        headers=_new_pre_auth_headers(client),
    )
    assert login.status_code == 200
    assert "token" not in login.json()
    assert db_session.query(UserSession).count() == 2


def test_login_registration_reject_missing_invalid_csrf_and_origin(client):
    payload = {
        "email": "person@example.com",
        "password": "SecurePassword123!",  # pragma: allowlist secret
    }
    missing = client.post("/api/v1/auth/login", json=payload)
    assert missing.status_code == 403

    valid_headers = _new_pre_auth_headers(client)
    invalid = client.post(
        "/api/v1/auth/login",
        json=payload,
        headers={**valid_headers, "X-CSRF-Token": "invalid"},
    )
    assert invalid.status_code == 403

    bad_origin = client.post(
        "/api/v1/auth/register",
        json=payload,
        headers={**valid_headers, "Origin": "https://attacker.example"},
    )
    assert bad_origin.status_code == 403

    no_origin = client.post(
        "/api/v1/auth/register",
        json=payload,
        headers={"X-CSRF-Token": valid_headers["X-CSRF-Token"]},
    )
    assert no_origin.status_code == 403


def test_expired_and_revoked_sessions_are_rejected(
    client, db_session, test_user_a, auth_headers_user_a
):
    user_session = db_session.query(UserSession).one()
    user_session.expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    db_session.commit()
    assert client.get("/api/v1/auth/me", headers=auth_headers_user_a).status_code == 401

    user_session.expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(days=1)
    user_session.revoked_at = dt.datetime.now(dt.UTC)
    db_session.commit()
    assert client.get("/api/v1/auth/me", headers=auth_headers_user_a).status_code == 401


def test_logout_revokes_session_and_clears_cookies(client, db_session, auth_headers_user_a):
    user_session = db_session.query(UserSession).one()
    res = client.post("/api/v1/auth/logout", headers=auth_headers_user_a)
    assert res.status_code == 204
    db_session.refresh(user_session)
    assert user_session.revoked_at is not None
    assert client.get("/api/v1/auth/me", headers=auth_headers_user_a).status_code == 401
    assert any(
        cookie.startswith(settings.session_cookie_name + "=") and "max-age=0" in cookie.lower()
        for cookie in res.headers.get_list("set-cookie")
    )


def test_logout_of_expired_session_is_safe(client, db_session, auth_headers_user_a):
    user_session = db_session.query(UserSession).one()
    user_session.expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    db_session.commit()
    res = client.post("/api/v1/auth/logout", headers=auth_headers_user_a)
    assert res.status_code == 204
    db_session.refresh(user_session)
    assert user_session.revoked_at is not None


def test_authenticated_state_changes_require_valid_csrf(client, auth_headers_user_a):
    data = {"job_description": "This request should be rejected before analysis."}
    missing = client.post(
        "/api/v1/analyze",
        data=data,
        headers={k: v for k, v in auth_headers_user_a.items() if k != "X-CSRF-Token"},
    )
    invalid = client.post(
        "/api/v1/analyze",
        data=data,
        headers={**auth_headers_user_a, "X-CSRF-Token": "invalid"},
    )
    valid = client.post("/api/v1/analyze", data=data, headers=auth_headers_user_a)
    assert missing.status_code == 403
    assert invalid.status_code == 403
    assert valid.status_code == 422


def test_session_cookie_is_secure_and_host_prefixed_in_production(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "prod")
    response = Response()
    set_session_cookie(response, "opaque-session-value", 60)
    cookie = _set_cookie_headers(response, "__Host-resumefit_session")
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "path=/" in cookie
    assert "domain=" not in cookie


@pytest.mark.parametrize(
    "values",
    [
        {"SECRET_KEY": "short"},
        {
            "APP_ENV": "prod",
            "SECRET_KEY": "development-secret-that-is-long-enough",  # pragma: allowlist secret
            "DATABASE_URL": "postgresql://db.example/resumefit",
            "ALLOWED_ORIGINS": ["https://resumefit.example"],
            "ALLOWED_HOSTS": ["resumefit.example"],
        },
        {
            "APP_ENV": "prod",
            "SECRET_KEY": "secure-production-key-value-with-sufficient-length",  # pragma: allowlist secret
            "DATABASE_URL": "sqlite:///./app.db",
            "ALLOWED_ORIGINS": ["https://resumefit.example"],
            "ALLOWED_HOSTS": ["resumefit.example"],
        },
        {
            "APP_ENV": "prod",
            "SECRET_KEY": "secure-production-key-value-with-sufficient-length",  # pragma: allowlist secret
            "DATABASE_URL": "postgresql://db.example/resumefit",
        },
    ],
)
def test_unsafe_configuration_is_rejected(values):
    with pytest.raises(ValidationError):
        Settings(**values)


def test_production_settings_require_explicit_signing_secret(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="prod",
            DATABASE_URL="postgresql://db.example/resumefit",
            ALLOWED_ORIGINS=["https://resumefit.example"],
            ALLOWED_HOSTS=["resumefit.example"],
        )


def test_application_import_rejects_missing_production_secret(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.pop("SECRET_KEY", None)
    env.update(
        {
            "APP_ENV": "prod",
            "DATABASE_URL": "postgresql://db.example/resumefit",
            "ALLOWED_ORIGINS": '["https://resumefit.example"]',
            "ALLOWED_HOSTS": '["resumefit.example"]',
            "PYTHONPATH": str(project_root),
        }
    )
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode != 0
    assert "SECRET_KEY" in result.stderr
