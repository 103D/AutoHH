"""Data model for the deterministic scoring engine (match model v3).

A vacancy defines *skill requirements* classified by importance:

    REQUIRED  — mandatory skills; their absence is always visible
    PREFERRED — strong plus, weighted more than optional
    OPTIONAL  — nice-to-have / generic mentions

Each requirement gets a *match status* derived from the candidate profile:

    MATCHED  — candidate has the skill (exact / alias via taxonomy)
    PARTIAL  — candidate has a transferable/predecessor skill (LLM-equivalent)
    MISSING  — candidate does not have the skill
    UNKNOWN  — no candidate skill data to judge against

The technical score is a weighted requirement-coverage metric — NOT the
candidate-skills coverage used by earlier versions. Importance weights make
REQUIRED skills dominate; a missing REQUIRED skill additionally lowers the
final score through an explicit cap (``score_caps``) and is listed separately
in ``SkillAudit.missing_required`` so it can never disappear inside the
aggregate number.

This module intentionally stays dependency-free (pure dataclasses) so the
scoring model can be unit-tested in isolation and shared across the engine,
matching orchestration and the API serialization layer.
"""

from dataclasses import dataclass, field
from typing import Any

# Requirement importance
REQUIRED = "REQUIRED"
PREFERRED = "PREFERRED"
OPTIONAL = "OPTIONAL"
IMPORTANCE_LEVELS = (REQUIRED, PREFERRED, OPTIONAL)

# Per-requirement match status
MATCHED = "MATCHED"
PARTIAL = "PARTIAL"
MISSING = "MISSING"
UNKNOWN = "UNKNOWN"

# Relative weight of each importance level in the weighted mean.
REQUIRED_WEIGHT = 3.0
PREFERRED_WEIGHT = 1.5
OPTIONAL_WEIGHT = 0.5

DEFAULT_IMPORTANCE_WEIGHTS: dict[str, float] = {
    REQUIRED: REQUIRED_WEIGHT,
    PREFERRED: PREFERRED_WEIGHT,
    OPTIONAL: OPTIONAL_WEIGHT,
}

# Value contributed by each status inside the weighted mean.
STATUS_VALUE: dict[str, float] = {
    MATCHED: 1.0,
    PARTIAL: 0.5,
    MISSING: 0.0,
    UNKNOWN: 0.0,
}

# Where the requirement list came from (explainability).
REQ_SOURCE_DETERMINISTIC = "deterministic"
REQ_SOURCE_LLM = "llm"
REQ_SOURCE_HEURISTIC = "heuristic"


@dataclass
class RequirementMatch:
    """One extracted job requirement with its candidate match status."""

    skill: str
    importance: str
    status: str = MISSING
    source: str = REQ_SOURCE_DETERMINISTIC
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill": self.skill,
            "importance": self.importance,
            "status": self.status,
            "source": self.source,
            "note": self.note,
        }


@dataclass
class SkillAudit:
    """Explainability record for the technical score component.

    ``source`` tells how the requirement list was obtained:
    - ``deterministic``: requirements were extracted by the deterministic
      section/marker scanner; the technical score is the weighted requirement
      coverage;
    - ``llm``: requirements were extracted by the LLM and re-scored
      deterministically;
    - ``heuristic``: no usable requirements — legacy candidate-coverage
      scoring was used as a fallback.
    """

    source: str = REQ_SOURCE_HEURISTIC
    requirements: list[RequirementMatch] = field(default_factory=list)
    matched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "required": [
                r.to_dict() for r in self.requirements if r.importance == REQUIRED
            ],
            "preferred": [
                r.to_dict() for r in self.requirements if r.importance == PREFERRED
            ],
            "optional": [
                r.to_dict() for r in self.requirements if r.importance == OPTIONAL
            ],
            "missing_required": list(self.missing_required),
            "matched": list(self.matched),
            "missing": list(self.missing),
            "unknown": list(self.unknown),
        }


@dataclass
class ScoreBreakdown:
    """Individual score components plus explainability (match model v3)."""

    technical: float = 0.0          # 0-100: weighted requirement coverage
    experience: float = 0.0         # 0-100: years/seniority match
    location: float = 0.0           # 0-100: location/remote match
    salary: float = 0.0             # 0-100: salary expectations match
    work_format: float = 0.0        # 0-100: remote/hybrid/office match
    education: float = 0.0          # 0-100: education match
    language: float = 0.0           # 0-100: language match

    # Explainability (match model v3). Kept in the same dataclass so the
    # aggregation logic (engine) and the API (to_full_dict) share one place.
    skills: SkillAudit | None = None
    score_caps: list[dict[str, Any]] = field(default_factory=list)
    llm_adjustments: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, float]:
        """Backward-compatible: component floats only (unchanged contract)."""
        return {
            "technical": round(self.technical, 1),
            "experience": round(self.experience, 1),
            "location": round(self.location, 1),
            "salary": round(self.salary, 1),
            "work_format": round(self.work_format, 1),
            "education": round(self.education, 1),
            "language": round(self.language, 1),
        }

    def to_full_dict(self) -> dict[str, Any]:
        """Full serializable breakdown incl. skill audit / caps / LLM deltas."""
        result: dict[str, Any] = self.to_dict()
        if self.skills is not None:
            result["skills"] = self.skills.to_dict()
        if self.score_caps:
            result["score_caps"] = list(self.score_caps)
        if self.llm_adjustments:
            result["llm_adjustments"] = dict(self.llm_adjustments)
        return result
