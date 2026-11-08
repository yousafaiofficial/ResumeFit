def test_healthz_liveness(client):
    res = client.get("/healthz")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "timestamp" in data
    assert "version" in data


def test_readyz_readiness(client):
    res = client.get("/readyz")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert data["database"] is True
    assert data["nlp_model_loaded"] is True


def test_readyz_returns_safe_failure_when_database_is_unavailable(client, monkeypatch):
    import app.routers.api_v1.health as health

    monkeypatch.setattr(health, "check_db_health", lambda: False)
    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "database": False,
        "nlp_model_loaded": True,
    }
