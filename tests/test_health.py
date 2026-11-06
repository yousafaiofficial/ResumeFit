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
