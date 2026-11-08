"""Backwards compatibility shim for legacy nlp module."""

from app.services.nlp_service import (
    analyze,
    backend_name,
    find_skills,
    llm_rewrite,
    rule_rewrite,
    semantic_similarity,
    weak_bullets,
)
from app.services.pdf_service import extract_pdf_text

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
