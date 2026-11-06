"""Backwards compatibility shim for legacy nlp module."""
from app.services.pdf_service import extract_pdf_text
from app.services.nlp_service import (
    analyze,
    backend_name,
    find_skills,
    semantic_similarity,
    weak_bullets,
    rule_rewrite,
    llm_rewrite,
)

__all__ = [
    "extract_pdf_text",
    "analyze",
    "backend_name",
    "find_skills",
    "semantic_similarity",
    "weak_bullets",
    "rule_rewrite",
    "llm_rewrite",
]
