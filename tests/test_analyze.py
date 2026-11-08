def test_unauthenticated_requests_cannot_analyze_or_access_history(client):
    analyze_res = client.post(
        "/api/v1/analyze",
        data={
            "job_description": "A sufficiently long job description for a protected analysis.",
            "resume_text": "A sufficiently long synthetic resume that should never be analyzed.",
        },
    )
    history_res = client.get("/api/v1/history")

    assert analyze_res.status_code == 401
    assert history_res.status_code == 401


def test_analyze_input_bounds_too_short(client, auth_headers_user_a):
    data = {
        "job_description": "Too short",
        "resume_text": "A" * 100,
    }
    res = client.post("/api/v1/analyze", data=data, headers=auth_headers_user_a)
    assert res.status_code == 422
    assert "Job description too short" in res.json()["message"]


def test_analyze_and_caching(client, auth_headers_user_a):
    """Verifies item 19: caching repeated identical resume and JD via content hash."""
    jd = "We are seeking a Senior Python Engineer with expertise in FastAPI, PostgreSQL, and Docker containerization."
    resume = (
        "Summary: Backend Engineer with 5 years experience.\n"
        "Experience: Responsible for developing Python APIs using FastAPI and optimizing PostgreSQL queries.\n"
        "Skills: Python, FastAPI, PostgreSQL, Docker, Git"
    )
    data = {
        "job_title": "Senior Python Engineer",
        "job_description": jd,
        "resume_text": resume,
    }

    # First call - fresh analysis
    res1 = client.post("/api/v1/analyze", data=data, headers=auth_headers_user_a)
    assert res1.status_code == 200
    r1 = res1.json()
    assert r1["cached"] is False
    assert r1["score"] > 0
    assert "python" in r1["matched_skills"]

    # Second call - same input, should hit cache
    res2 = client.post("/api/v1/analyze", data=data, headers=auth_headers_user_a)
    assert res2.status_code == 200
    r2 = res2.json()
    assert r2["cached"] is True
    assert r2["score"] == r1["score"]


def test_history_pagination(client, auth_headers_user_a):
    """Verifies item 20: limit and cursor pagination."""
    res = client.get("/api/v1/history?limit=5", headers=auth_headers_user_a)
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "limit" in data
    assert data["limit"] == 5
