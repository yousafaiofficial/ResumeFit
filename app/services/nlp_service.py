"""Pure NLP service: text similarity, skill extraction with taxonomy aliases, and bullet rewrites."""
import hashlib
import json
import os
import re
from functools import lru_cache
from typing import Any
import numpy as np
from app.core.config import settings

_model_loaded: bool = False

# ---------- Skill Taxonomy & Aliases (Item 51) ----------

SKILL_ALIASES: dict[str, str] = {
    "k8s": "kubernetes",
    "kube": "kubernetes",
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "postgres": "postgresql",
    "pgsql": "postgresql",
    "golang": "go",
    "reactjs": "react",
    "react.js": "react",
    "vuejs": "vue",
    "vue.js": "vue",
    "nextjs": "next.js",
    "nodejs": "node.js",
    "node": "node.js",
    "tf": "terraform",
    "es": "elasticsearch",
    "mongo": "mongodb",
    "ml": "machine learning",
    "dl": "deep learning",
    "nlp": "natural language processing",
    "gcp": "gcp",
    "aws": "aws",
    "rest": "rest api",
    "ci/cd": "ci/cd",
    "cicd": "ci/cd",
    "gh actions": "github actions",
}

SINGLE_SKILLS = """python java javascript typescript c++ c# go rust ruby php swift kotlin scala sql nosql matlab bash
react angular vue next.js node.js express django flask fastapi spring .net html css sass tailwind graphql
postgresql mysql mongodb redis elasticsearch sqlite kafka rabbitmq spark hadoop airflow dbt snowflake bigquery
aws azure gcp docker kubernetes terraform ansible jenkins ci/cd linux git microservices
nlp pytorch tensorflow scikit-learn pandas numpy llm transformers etl tableau excel statistics
agile scrum jira leadership communication mentoring testing pytest junit selenium security oauth devops sre
monitoring prometheus grafana figma ux""".split()

MULTI_SKILLS = [
    "machine learning",
    "deep learning",
    "natural language processing",
    "computer vision",
    "data analysis",
    "data engineering",
    "a/b testing",
    "power bi",
    "github actions",
    "product management",
    "project management",
    "stakeholder management",
    "rest api",
    "unit testing",
    "cloud computing",
]

# Combined canonical skill taxonomy
CANONICAL_SKILLS = sorted(set(SINGLE_SKILLS + MULTI_SKILLS), key=len, reverse=True)


# ---------- Embedding Model Management (Item 63) ----------

@lru_cache(maxsize=1)
def _load_model():
    global _model_loaded
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(settings.EMBED_MODEL)
        _model_loaded = True
        return model
    except Exception as e:
        # Graceful fallback to TF-IDF when heavy dependencies are absent
        _model_loaded = False
        return None


def warmup_model() -> None:
    """Preloads and warms up embedding model at application startup."""
    try:
        model = _load_model()
        if model is not None:
            model.encode(["warmup sentence"])
    except Exception:
        pass


def is_model_ready() -> bool:
    """Readiness probe status for ML model."""
    return _load_model() is not None or True  # TF-IDF fallback is always ready


def backend_name() -> str:
    return "sentence-transformers" if _load_model() is not None else "tfidf-fallback"


def compute_content_hash(resume_text: str, jd_text: str) -> str:
    """Computes deterministic SHA256 hash of resume + JD for caching (item 19)."""
    hasher = hashlib.sha256()
    hasher.update(resume_text.strip().encode("utf-8"))
    hasher.update(b"---DELIMITER---")
    hasher.update(jd_text.strip().encode("utf-8"))
    return hasher.hexdigest()


# ---------- Embeddings and Similarity ----------

def _chunk(text: str, target: int = 220) -> list[str]:
    out, buf = [], ""
    for line in (l.strip() for l in text.splitlines()):
        if not line:
            continue
        buf = f"{buf} {line}".strip()
        if len(buf) >= target:
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return out or [text]


def _embed(chunks: list[str]) -> np.ndarray:
    model = _load_model()
    if model is not None:
        return np.asarray(model.encode(chunks, normalize_embeddings=True))
    from sklearn.feature_extraction.text import TfidfVectorizer

    vec = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", sublinear_tf=True)
    return vec.fit_transform(chunks).toarray()


def semantic_similarity(resume: str, jd: str) -> float:
    """0-100 similarity score blending overall-document and chunk-level coverage."""
    rc, jc = _chunk(resume), _chunk(jd)
    emb = _embed(rc + jc)
    r, j = emb[: len(rc)], emb[len(rc) :]
    norm = lambda v: v / (np.linalg.norm(v) + 1e-9)
    global_sim = float(norm(r.mean(0)) @ norm(j.mean(0)))
    coverage = float((j @ r.T).max(axis=1).mean())
    raw = 0.5 * global_sim + 0.5 * coverage
    lo, hi = (0.15, 0.65) if _load_model() is not None else (0.0, 0.30)
    return round(float(np.clip((raw - lo) / (hi - lo), 0, 1)) * 100, 1)


# ---------- Skill Extraction with Aliases ----------

def find_skills(text: str) -> set[str]:
    t = text.lower()
    found: set[str] = set()

    # 1. Direct canonical skills
    for s in CANONICAL_SKILLS:
        if re.search(rf"(?<![a-z0-9+#]){re.escape(s)}(?![a-z0-9+#])", t):
            found.add(s)

    # 2. Skill aliases mapping to canonical
    for alias, canonical in SKILL_ALIASES.items():
        if re.search(rf"(?<![a-z0-9+#]){re.escape(alias)}(?![a-z0-9+#])", t):
            found.add(canonical)

    return found


# ---------- Sections & Suggestions ----------

SECTIONS = {
    "summary": r"\b(summary|profile|objective)\b",
    "experience": r"\b(experience|employment|work history)\b",
    "education": r"\beducation\b",
    "skills": r"\bskills\b",
    "projects": r"\bprojects?\b",
}

WEAK = [
    (r"^(responsible for|duties included)\s+", "Led "),
    (r"^(worked on|worked with)\s+", "Delivered "),
    (r"^(helped|helped to)\s+", "Contributed to "),
    (r"^(assisted with|assisted in)\s+", "Supported "),
    (r"^(involved in|participated in)\s+", "Drove "),
    (r"^(was tasked with|tasked with)\s+", "Executed "),
]


def _bullets(resume: str) -> list[str]:
    out = []
    for line in resume.splitlines():
        s = re.sub(r"^[\s•\-\*▪◦●·]+", "", line).strip()
        words = s.split()
        n = len(words)
        if 35 <= len(s) <= 260 and n >= 6 and s.count(",") / n < 0.5:
            out.append(s)
    return out


def weak_bullets(resume: str, limit: int = 5) -> list[str]:
    scored = []
    for b in _bullets(resume):
        weak = any(re.search(p, b.lower()) for p, _ in WEAK)
        no_metric = not re.search(r"\d", b)
        if weak or no_metric:
            scored.append((2 * weak + no_metric, b))
    scored.sort(key=lambda x: -x[0])
    return [b for _, b in scored[:limit]]


def rule_rewrite(b: str, missing: list[str]) -> str:
    out = b
    for pat, rep in WEAK:
        if re.search(pat, out.lower()):
            out = re.sub(pat, rep, out, flags=re.I)
            break
    out = out[0].upper() + out[1:]
    if not re.search(r"\d", out):
        out = out.rstrip(".") + ", [quantify: % improved, $ saved, users, time]."
    return out


def llm_rewrite(bullets: list[str], missing: list[str], jd: str) -> list[dict[str, str]] | None:
    key = settings.ANTHROPIC_API_KEY
    if not key or not bullets:
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=key)
        prompt = (
            "Rewrite each resume bullet to be stronger for the job description below. Rules: start with a strong "
            "action verb, stay truthful (never invent numbers; use [metric] placeholders), work in relevant missing "
            "keywords only if the bullet plausibly supports them, max 28 words each.\n"
            f"Missing keywords: {', '.join(missing[:10]) or 'none'}\n"
            f"Job description:\n{jd[:2500]}\n\nBullets:\n"
            + "\n".join(f"{i+1}. {b}" for i, b in enumerate(bullets))
            + '\n\nReturn ONLY a JSON array of {"original": str, "suggested": str}.'
        )
        msg = client.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
        data = json.loads(text)
        return [
            {"original": d["original"], "suggested": d["suggested"], "source": "ai"}
            for d in data
        ][: len(bullets)]
    except Exception:
        return None


# ---------- Main Analysis Function ----------

def analyze(resume: str, jd: str) -> dict[str, Any]:
    sem = semantic_similarity(resume, jd)
    r_sk, j_sk = find_skills(resume), find_skills(jd)
    matched, missing = sorted(j_sk & r_sk), sorted(j_sk - r_sk)
    skill_score = round(100 * len(matched) / len(j_sk), 1) if j_sk else None
    score = round(0.6 * sem + 0.4 * skill_score, 1) if skill_score is not None else sem

    sections = {k: bool(re.search(p, resume, re.I)) for k, p in SECTIONS.items()}
    words = len(resume.split())

    tips = []
    if missing:
        tips.append(
            f"Add evidence for {', '.join(missing[:6])}. Only include skills you genuinely have, "
            "and show them inside experience bullets, not just a skills list."
        )
    for name in ("summary", "skills"):
        if not sections.get(name):
            tips.append(f"Add a {name.title()} section so recruiters and ATS parsers find it quickly.")
    if words < 250:
        tips.append("Your resume is short. Add detail on scope, tools and outcomes for each role.")
    elif words > 900:
        tips.append("Your resume is long. Aim for one page per ~8 years of experience; cut older or low-impact items.")
    if len(re.findall(r"\d+%|\$\d|\b\d{2,}\b", resume)) < 4:
        tips.append("Few measurable results found. Add numbers: percentages, revenue, users, latency, time saved.")

    bullets = weak_bullets(resume)
    rewrites = llm_rewrite(bullets, missing, jd) or [
        {"original": b, "suggested": rule_rewrite(b, missing), "source": "rules"}
        for b in bullets
    ]

    return {
        "score": score,
        "semantic_score": sem,
        "skill_score": skill_score,
        "matched_skills": matched,
        "missing_skills": missing,
        "sections": sections,
        "word_count": words,
        "suggestions": tips,
        "rewrites": rewrites,
        "engine": backend_name(),
    }
