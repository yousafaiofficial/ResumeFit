import json
from app.models.analysis import Analysis


def test_tenant_isolation_read(client, db_session, test_user_a, test_user_b, auth_headers_user_a, auth_headers_user_b):
    """User B must not be able to read User A's analysis record."""
    # Create analysis owned by User A
    analysis_a = Analysis(
        user_id=test_user_a.id,
        job_title="User A Secret Job",
        score=85.0,
        result_json=json.dumps({
            "score": 85.0,
            "semantic_score": 80.0,
            "skill_score": 90.0,
            "matched_skills": ["python"],
            "missing_skills": [],
            "sections": {"experience": True},
            "word_count": 200,
            "suggestions": [],
            "rewrites": [],
            "engine": "test",
        }),
    )
    db_session.add(analysis_a)
    db_session.commit()
    db_session.refresh(analysis_a)

    # User A can read it
    res_a = client.get(f"/api/v1/history/{analysis_a.id}", headers=auth_headers_user_a)
    assert res_a.status_code == 200
    assert res_a.json()["job_title"] == "User A Secret Job"

    # User B cannot read it (must return 404)
    res_b = client.get(f"/api/v1/history/{analysis_a.id}", headers=auth_headers_user_b)
    assert res_b.status_code == 404
    assert res_b.json()["code"] == "HTTP_404"


def test_tenant_isolation_list(client, db_session, test_user_a, test_user_b, auth_headers_user_a, auth_headers_user_b):
    """User B's history listing must not contain User A's analyses."""
    analysis_a = Analysis(
        user_id=test_user_a.id,
        job_title="Role A",
        score=75.0,
        result_json=json.dumps({"score": 75.0, "word_count": 150, "engine": "test"}),
    )
    analysis_b = Analysis(
        user_id=test_user_b.id,
        job_title="Role B",
        score=90.0,
        result_json=json.dumps({"score": 90.0, "word_count": 300, "engine": "test"}),
    )
    db_session.add_all([analysis_a, analysis_b])
    db_session.commit()

    # User B lists history
    res = client.get("/api/v1/history", headers=auth_headers_user_b)
    assert res.status_code == 200
    data = res.json()
    items = data["items"]
    assert len(items) == 1
    assert items[0]["job_title"] == "Role B"
    assert not any(i["job_title"] == "Role A" for i in items)


def test_tenant_isolation_delete(client, db_session, test_user_a, test_user_b, auth_headers_user_b):
    """User B cannot delete User A's analysis record."""
    analysis_a = Analysis(
        user_id=test_user_a.id,
        job_title="Role A",
        score=80.0,
        result_json=json.dumps({"score": 80.0, "word_count": 220, "engine": "test"}),
    )
    db_session.add(analysis_a)
    db_session.commit()
    db_session.refresh(analysis_a)

    # User B attempts to delete User A's record
    res = client.delete(f"/api/v1/history/{analysis_a.id}", headers=auth_headers_user_b)
    assert res.status_code == 404

    # Verify record still exists in DB
    still_there = db_session.get(Analysis, analysis_a.id)
    assert still_there is not None
