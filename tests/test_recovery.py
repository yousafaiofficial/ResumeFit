import datetime as dt
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.core.config import settings
from app.core.security import create_user_session, hash_secret_token, verify_password
from app.models.recovery import AuthChallenge, GoogleIdentity
from app.models.session import UserSession
from app.models.user import User
from app.routers.api_v1 import recovery


@pytest.fixture
def providers(monkeypatch):
    for key, value in {
        "PUBLIC_BASE_URL": "http://localhost:8000",
        "GOOGLE_CLIENT_ID": "client-id",
        "GOOGLE_CLIENT_SECRET": "fake-provider-secret",  # pragma: allowlist secret
        "RESEND_API_KEY": "fake-email-key",  # pragma: allowlist secret
        "EMAIL_FROM": "ResumeFit <noreply@example.invalid>",
    }.items():
        monkeypatch.setattr(settings, key, value)


def start_google(client):
    response = client.get("/api/v1/auth/google/start", follow_redirects=False)
    assert response.status_code == 303
    params = parse_qs(urlsplit(response.headers["location"]).query)
    assert params["code_challenge_method"] == ["S256"]
    assert "HttpOnly" in response.headers["set-cookie"]
    return params["state"][0]


def test_optional_providers_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", None)
    monkeypatch.setattr(settings, "RESEND_API_KEY", None)
    assert client.get("/api/v1/auth/options").json() == {"google": False, "password_reset": False}
    assert client.get("/api/v1/auth/google/start").status_code == 503


def test_google_success_and_replay(client, db_session, providers, monkeypatch):
    state = start_google(client)
    calls = []

    def exchange(code, verifier):
        calls.append((code, verifier))
        return {
            "sub": "stable-google-sub",
            "email": "google@example.invalid",
            "email_verified": True,
        }

    monkeypatch.setattr(recovery, "exchange_google", exchange)
    callback = f"/api/v1/auth/google/callback?state={state}&code=fake-code"
    response = client.get(callback, follow_redirects=False)
    assert response.headers["location"] == "/"
    assert client.get("/api/v1/auth/me").json()["email"] == "google@example.invalid"
    assert db_session.get(GoogleIdentity, "stable-google-sub") is not None
    assert len(calls) == 1
    client.get(callback, follow_redirects=False)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "invalid", ["mismatch", "expired", "unverified", "existing", "inactive", "cancel"]
)
def test_google_rejects_unsafe_logins(
    client, db_session, providers, monkeypatch, test_user_a, invalid
):
    state = start_google(client)
    if invalid == "expired":
        row = db_session.get(AuthChallenge, hash_secret_token(state))
        row.expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
        db_session.commit()
    if invalid == "inactive":
        test_user_a.is_active = False
        db_session.add(GoogleIdentity(subject="sub", user_id=test_user_a.id))
        db_session.commit()
    monkeypatch.setattr(
        recovery,
        "exchange_google",
        lambda *args: {
            "sub": "sub",
            "email": test_user_a.email if invalid == "existing" else "new@example.invalid",
            "email_verified": invalid != "unverified",
        },
    )
    callback_state = "wrong" if invalid == "mismatch" else state
    extra = "error=access_denied" if invalid == "cancel" else "code=fake-code"
    client.get(
        f"/api/v1/auth/google/callback?state={callback_state}&{extra}", follow_redirects=False
    )
    assert client.get("/api/v1/auth/me").status_code == 401
    assert db_session.query(User).count() == 1


def test_password_reset_hashed_single_use_revokes_sessions(
    client,
    db_session,
    providers,
    monkeypatch,
    test_user_a,
    pre_auth_headers,
):
    sent = []
    monkeypatch.setattr(
        recovery, "send_reset_email", lambda email, token: sent.append((email, token))
    )
    create_user_session(db_session, test_user_a)
    create_user_session(db_session, test_user_a)
    response = client.post(
        "/api/v1/auth/password/forgot", json={"email": test_user_a.email}, headers=pre_auth_headers
    )
    assert response.status_code == 200
    token = sent[0][1]
    row = db_session.query(AuthChallenge).filter_by(purpose="reset").one()
    assert row.token_hash == hash_secret_token(token)
    assert row.token_hash != token
    reset = {"token": token, "password": "ChangedPassword123!"}  # pragma: allowlist secret
    assert (
        client.post("/api/v1/auth/password/reset", json=reset, headers=pre_auth_headers).status_code
        == 200
    )
    db_session.refresh(test_user_a)
    assert verify_password(reset["password"], test_user_a.password_hash)
    assert all(row.revoked_at is not None for row in db_session.query(UserSession).all())
    headers = {
        "Origin": "http://localhost:8000",
        "X-CSRF-Token": client.get("/api/v1/auth/csrf").json()["csrf_token"],
    }
    assert (
        client.post("/api/v1/auth/password/reset", json=reset, headers=headers).status_code == 400
    )


def test_reset_generic_unknown_and_email_failure(
    client, providers, monkeypatch, test_user_a, pre_auth_headers
):
    def fail(*args):
        raise httpx.ConnectError("simulated delivery outage")

    monkeypatch.setattr(recovery, "send_reset_email", fail)
    known = client.post(
        "/api/v1/auth/password/forgot", json={"email": test_user_a.email}, headers=pre_auth_headers
    )
    unknown = client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "unknown@example.invalid"},
        headers=pre_auth_headers,
    )
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()


def test_reset_rejects_expiry_and_csrf(
    client, db_session, providers, test_user_a, pre_auth_headers
):
    token = "expired-token-with-enough-entropy-for-test"
    db_session.add(
        AuthChallenge(
            token_hash=hash_secret_token(token),
            purpose="reset",
            user_id=test_user_a.id,
            expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1),
        )
    )
    db_session.commit()
    payload = {"token": token, "password": "ChangedPassword123!"}  # pragma: allowlist secret
    assert client.post("/api/v1/auth/password/reset", json=payload).status_code == 403
    assert (
        client.post(
            "/api/v1/auth/password/reset", json=payload, headers=pre_auth_headers
        ).status_code
        == 400
    )
