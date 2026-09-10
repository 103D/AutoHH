"""Gap analysis service wrapper for Hermes.

Provides structured gap analysis between a candidate profile and a specific job,
combining deterministic scoring with skill/experience/salary gap metrics that
GPT-5.5 can reason about through Hermes MCP tools.

This service is deterministic — no AI calls. It adapts the existing
MatchingService.get_gap_analysis pipeline into a flat, JSON-serializable dict.
"""

from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


class GapAnalysisError(Exception):
    """Raised when gap analysis cannot be completed."""
    pass


@dataclass
class GapAnalysisResult:
    """Structured result of a gap analysis between candidate and job."""

    overall_score: int = 0
    match_level: str = "UNKNOWN"
    skill_gaps: list[str] = field(default_factory=list)
    experience_gap: float = 0.0
    salary_gap: int = 0
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "match_level": self.match_level,
            "skill_gaps": list(self.skill_gaps),
            "experience_gap": self.experience_gap,
            "salary_gap": self.salary_gap,
            "recommendations": list(self.recommendations),
        }


class HermesGapAnalysisService:
    """Service wrapper for deterministic skill/experience gap analysis.

    Accepts a context object (anything with a matching_service) and exposes
    a flat ``analyze_gap(job, match, profile)`` method that returns a
    JSON-serializable dict.
    """

    def __init__(self, ctx: Any):
        self._ctx = ctx

    async def analyze_gap(
        self,
        job: Any,
        match: Any,
        profile: Any,
    ) -> dict[str, Any]:
        """Return gap analysis as a JSON-serializable dict.

        Args:
            job: Job model instance.
            match: MatchResult model instance.
            profile: CandidateProfile model instance.

        Returns:
            Dict with keys: overall_score, match_level, skill_gaps,
            experience_gap, salary_gap, recommendations.
        """
        if match is None:
            raise GapAnalysisError("match result is None")

        score = int(getattr(match, "score", 0) or 0)
        recommendation = getattr(match, "recommendation", "UNKNOWN") or "UNKNOWN"
        missing_skills = list(getattr(match, "missing_skills", None) or [])

        # Experience gap
        job_exp = getattr(job, "experience_required", None)
        profile_exp = getattr(profile, "experience_years", None)
        experience_gap = 0.0
        if job_exp is not None and profile_exp is not None:
            experience_gap = max(0.0, float(job_exp) - float(profile_exp))

        # Salary gap: how much the candidate's minimum exceeds the job's maximum
        job_salary_max = getattr(job, "salary_max", None)
        profile_desired_min = getattr(profile, "desired_salary_min", None)
        salary_gap = 0
        if profile_desired_min is not None and job_salary_max is not None:
            gap = profile_desired_min - job_salary_max
            if gap > 0:
                salary_gap = int(gap)

        # Build recommendations
        recommendations: list[str] = []
        if missing_skills:
            recommendations.append(
                f"Consider learning: {', '.join(missing_skills[:5])}"
            )
        if experience_gap > 0:
            recommendations.append(
                f"Vacancy requires {int(job_exp) if job_exp else 0}+ years "
                f"experience; you have {int(profile_exp) if profile_exp else 0}"
            )
        if salary_gap > 0:
            recommendations.append(
                f"Your minimum desired salary {profile_desired_min} exceeds "
                f"the job's maximum {job_salary_max}"
            )
        if not recommendations:
            recommendations.append("Candidate profile aligns well with this vacancy")

        return GapAnalysisResult(
            overall_score=score,
            match_level=recommendation,
            skill_gaps=missing_skills,
            experience_gap=experience_gap,
            salary_gap=salary_gap,
            recommendations=recommendations,
        ).to_dict()
