def test_csrf_token_endpoint(client):
    res = client.get("/api/v1/auth/csrf")
    assert res.status_code == 200
    data = res.json()
    assert "csrf_token" in data
    assert len(data["csrf_token"]) == 64


def test_register_enforces_password_length(client):
    """Item 32: Sensible password policy - minimum 10 characters."""
    payload = {"email": "shortpw@example.com", "password": "short"}
    res = client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 422
    assert res.json()["code"] == "VALIDATION_ERROR"


def test_register_and_login_success(client):
    payload = {"email": "newuser@example.com", "password": "SuperSecurePassword123!"}
    reg_res = client.post("/api/v1/auth/register", json=payload)
    assert reg_res.status_code == 201
    assert "token" in reg_res.json()
    assert reg_res.json()["email"] == "newuser@example.com"
    # Ensure session cookie was set
    assert "resumefit_session" in reg_res.cookies

    # Login
    login_res = client.post("/api/v1/auth/login", json=payload)
    assert login_res.status_code == 200
    assert "token" in login_res.json()


def test_login_invalid_credentials(client):
    res = client.post(
        "/api/v1/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "RandomPassword123!",  # pragma: allowlist secret
        },
    )
    assert res.status_code == 401
    assert res.json()["code"] == "HTTP_401"
