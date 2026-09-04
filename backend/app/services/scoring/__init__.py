"""Deterministic scoring engine (match model v3).

Public API stays stable — ``from app.services.scoring import ScoringEngine``
and ``ScoreBreakdown`` keep working:

    engine = ScoringEngine(weights=...)           # optional per-candidate weights
    score, breakdown = engine.calculate(candidate, job)
    engine.get_recommendation(score)

The package is split into bounded components:

- ``model``: ScoreBreakdown / SkillAudit / RequirementMatch data model;
- ``skills``: requirement extraction + matching + technical score;
- ``experience`` / ``location`` / ``salary`` / ``work_format`` /
  ``education_language``: one component each;
- ``engine``: aggregation, caps, recommendation mapping, LLM-merge entry.
"""

from app.services.scoring.engine import ScoringEngine
from app.services.scoring.model import (
    MATCHED,
    MISSING,
    OPTIONAL,
    PARTIAL,
    PREFERRED,
    REQUIRED,
    UNKNOWN,
    RequirementMatch,
    ScoreBreakdown,
    SkillAudit,
)

__all__ = [
    "ScoringEngine",
    "ScoreBreakdown",
    "SkillAudit",
    "RequirementMatch",
    "REQUIRED",
    "PREFERRED",
    "OPTIONAL",
    "MATCHED",
    "PARTIAL",
    "MISSING",
    "UNKNOWN",
]
