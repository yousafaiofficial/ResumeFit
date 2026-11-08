import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_demo_is_synthetic_and_has_no_authenticated_side_effects():
    script = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")
    page = (PROJECT_ROOT / "static" / "index.html").read_text(encoding="utf-8")

    assert not re.search(r"recruiter[-_]demo@", script, re.IGNORECASE)
    assert not re.search(r"DemoCandidate\d{4}!", script)
    assert "demoEmail" not in script
    assert "demoPass" not in script

    demo_handler = script.split("function showDemo() {", 1)[1].split("\n}", 1)[0]
    for side_effect in ("api(", "fetch(", "localStorage", "resumeText", '"jd"'):
        assert side_effect not in demo_handler

    assert "const SAMPLE_ANALYSIS =" in script
    assert 'showResult(SAMPLE_ANALYSIS, $("demoResults"), true)' in demo_handler
    assert "if (token && !demoMode)" in script
    assert "if (!token || demoMode) return;" in script
    assert "Illustrative sample only" in script
    assert "not an analysis of your resume or a real job posting" in page


def test_real_analysis_is_blocked_in_frontend_without_authentication():
    script = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")

    assert "if (!token || demoMode) {" in script
    assert "Sign in to analyze and save a resume." in script
