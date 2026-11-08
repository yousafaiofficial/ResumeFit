import json

from app.models.analysis import Analysis


def test_tenant_isolation_read(
    client, db_session, test_user_a, test_user_b, auth_headers_user_a, auth_headers_user_b
):
    """User A must not be able to read User B's analysis record."""
    analysis_b = Analysis(
        user_id=test_user_b.id,
        job_title="User B Secret Job",
        score=85.0,
        result_json=json.dumps(
            {
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
            }
        ),
    )
    db_session.add(analysis_b)
    db_session.commit()
    db_session.refresh(analysis_b)

    res_b = client.get(f"/api/v1/history/{analysis_b.id}", headers=auth_headers_user_b)
    assert res_b.status_code == 200
    assert res_b.json()["job_title"] == "User B Secret Job"

    res_a = client.get(f"/api/v1/history/{analysis_b.id}", headers=auth_headers_user_a)
    assert res_a.status_code == 404
    assert res_a.json()["code"] == "HTTP_404"


def test_tenant_isolation_list(
    client, db_session, test_user_a, test_user_b, auth_headers_user_a, auth_headers_user_b
):
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


def test_tenant_isolation_delete(client, db_session, test_user_a, test_user_b, auth_headers_user_a):
    """User A cannot delete User B's analysis record."""
    analysis_b = Analysis(
        user_id=test_user_b.id,
        job_title="Role B",
        score=80.0,
        result_json=json.dumps({"score": 80.0, "word_count": 220, "engine": "test"}),
    )
    db_session.add(analysis_b)
    db_session.commit()
    db_session.refresh(analysis_b)

    res = client.delete(f"/api/v1/history/{analysis_b.id}", headers=auth_headers_user_a)
    assert res.status_code == 404

    # Verify record still exists in DB
    still_there = db_session.get(Analysis, analysis_b.id)
    assert still_there is not None
