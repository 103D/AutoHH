"""Skill/experience gap analysis (orphaned from MatchingService).

Turns a persisted MatchResult into the API-facing list of gaps. Requires the
stretch classifier only for its deterministic helpers (missing key skills and
required-experience extraction).
"""

from typing import TYPE_CHECKING

from app.models.candidate import CandidateProfile
from app.models.job import Job
from app.models.matching import MatchResult
from app.schemas.matching import GapItem

if TYPE_CHECKING:
    from app.services.stretch_classifier import StretchClassifier


def build_gap_items(
    profile: CandidateProfile,
    job: Job,
    match: MatchResult,
    stretch_classifier: "StretchClassifier",
) -> list[GapItem]:
    """Build the skill/experience gap list for a job.

    Missing REQUIRED skills (from the explainable breakdown) are surfaced
    first as high-priority gaps; everything else degrades to the legacy
    deterministic missing-skill list.
    """
    gaps: list[GapItem] = []

    breakdown_required = _missing_required_from_breakdown(match)
    for skill in breakdown_required:
        gaps.append(GapItem(skill=skill, gap_type="missing", priority="high"))

    missing = list(match.missing_skills or [])
    if not missing:
        missing = stretch_classifier.find_missing_key_skills(profile, job)
    for skill in missing[:10]:
        if skill not in breakdown_required:
            gaps.append(GapItem(skill=skill, gap_type="missing", priority="high"))

    required_years = stretch_classifier.extract_required_experience(job)
    if required_years and profile.experience_years is not None:
        if required_years > profile.experience_years:
            gaps.append(
                GapItem(
                    skill=f"{required_years}+ years experience",
                    gap_type="experience",
                    priority="medium",
                )
            )
    return gaps


def _missing_required_from_breakdown(match: MatchResult) -> list[str]:
    """Extract missing REQUIRED skills from the persisted breakdown (v3)."""
    breakdown = match.score_breakdown or {}
    skills = breakdown.get("skills") if isinstance(breakdown, dict) else None
    if not isinstance(skills, dict):
        return []
    return [str(s) for s in (skills.get("missing_required") or [])]
