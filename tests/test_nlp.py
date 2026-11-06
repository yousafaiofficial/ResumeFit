from app.services.nlp_service import (
    analyze,
    compute_content_hash,
    find_skills,
    rule_rewrite,
    semantic_similarity,
    weak_bullets,
)


def test_find_skills_canonical():
    text = "Proficient in Python, PostgreSQL, Docker, and Kubernetes."
    skills = find_skills(text)
    assert "python" in skills
    assert "postgresql" in skills
    assert "docker" in skills
    assert "kubernetes" in skills


def test_find_skills_aliases():
    """Validates item 51: skill aliases map to canonical terms (k8s -> kubernetes, etc)."""
    text = "Built microservices using k8s, js, ts, and postgres."
    skills = find_skills(text)
    assert "kubernetes" in skills  # k8s -> kubernetes
    assert "javascript" in skills  # js -> javascript
    assert "typescript" in skills  # ts -> typescript
    assert "postgresql" in skills  # postgres -> postgresql


def test_semantic_similarity_range():
    resume = "Senior Python engineer building high-concurrency microservices with FastAPI, Redis, and Postgres."
    jd = "Seeking Senior Python developer with FastAPI and relational database skills."
    score = semantic_similarity(resume, jd)
    assert isinstance(score, float)
    assert 0.0 <= score <= 100.0
    assert score > 30.0  # Should reflect relevance


def test_weak_bullet_detection():
    resume = (
        "Experience:\n"
        "• Responsible for building internal tools and fixing bugs\n"
        "• Led team of 5 engineers to deliver core payment gateway generating $4M in revenue\n"
        "• Assisted with legacy database migrations across multiple staging environments\n"
    )
    detected = weak_bullets(resume)
    assert len(detected) >= 2
    # The strong quantified bullet should not be flagged as top weak bullet
    assert any("Responsible for" in b for b in detected)
    assert any("Assisted with" in b for b in detected)


def test_rule_rewrite_enhancement():
    bullet = "responsible for building rest api endpoints"
    rewritten = rule_rewrite(bullet, missing=["FastAPI", "PostgreSQL"])
    assert rewritten.startswith("Led ")
    assert "[quantify:" in rewritten


def test_compute_content_hash_deterministic():
    resume = "Software Engineer with Python skills"
    jd = "Python Developer wanted"
    hash1 = compute_content_hash(resume, jd)
    hash2 = compute_content_hash(resume, jd)
    hash3 = compute_content_hash(resume + " extra", jd)

    assert hash1 == hash2
    assert len(hash1) == 64
    assert hash1 != hash3


def test_full_analyze_structure():
    resume = (
        "Summary\n"
        "Senior Backend Developer with 5 years experience.\n"
        "Experience\n"
        "• Responsible for designing microservices in Python and Docker.\n"
        "Skills\n"
        "Python, Docker, Kubernetes, SQL"
    )
    jd = "Looking for Senior Developer with Python, Docker, Kubernetes, and AWS experience."
    res = analyze(resume, jd)

    assert "score" in res
    assert "matched_skills" in res
    assert "missing_skills" in res
    assert "rewrites" in res
    assert "python" in res["matched_skills"]
    assert "aws" in res["missing_skills"]
