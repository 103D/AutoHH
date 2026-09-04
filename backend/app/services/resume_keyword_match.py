"""Keyword-coverage of a free-text resume against a vacancy.

Used by POST /matching/resume/match. Pure function — no ORM, no AI — so the
endpoint stays a thin adapter.
"""

from app.models.job import Job
from app.services.scoring.tokenize import tokenize_text

# Tokens too common to be meaningful coverage signals.
_COMMON_WORDS = {
    "the", "and", "for", "with", "you", "are", "our", "your", "this",
    "that", "from", "have", "will", "can", "not", "but", "all", "any",
    "who", "what", "when", "how", "why", "was", "were", "been", "being",
    "their", "there", "them", "then", "than", "into", "out", "about",
    "they", "she", "him", "her", "his", "its", "one", "two", "new",
    "use", "used", "using", "get", "got", "put", "set", "let",
}


def keyword_coverage(resume_text: str, job: Job) -> dict:
    """Coverage percentage plus matched/missing meaningful keywords."""

    resume_tokens = tokenize_text(resume_text)
    job_tokens = tokenize_text(f"{job.title} {job.description}")

    matched = resume_tokens & job_tokens
    missing = job_tokens - resume_tokens

    meaningful_matched = {t for t in matched if len(t) > 2 and t not in _COMMON_WORDS}
    meaningful_missing = {t for t in missing if len(t) > 2 and t not in _COMMON_WORDS}

    total = len(meaningful_matched) + len(meaningful_missing)
    coverage = round(len(meaningful_matched) / total * 100, 1) if total > 0 else 0.0

    return {
        "job_id": str(job.id),
        "job_title": job.title,
        "coverage_pct": coverage,
        "matched_keywords": sorted(meaningful_matched),
        "missing_keywords": sorted(meaningful_missing),
    }
