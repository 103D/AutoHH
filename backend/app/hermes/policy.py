"""User policy for autonomous actions.

In AUTONOMOUS mode Hermes may submit applications automatically, but only when
the vacancy satisfies the user's stated policy. The policy is a set of optional
guardrails that are AND-ed together — if any check fails, the application is
recommended for review rather than auto-submitted.
"""

from app.core.logging import get_logger
from app.models.candidate import CandidateProfile
from app.models.job import Job
from app.models.matching import MatchResult

logger = get_logger(__name__)


class UserPolicy:
    """Declarative guardrails for autonomous application submission.

    Every field is optional — an unset guard is not evaluated. This makes the
    policy forward-compatible: older deployments with partial configuration
    still work, just with fewer constraints.
    """

    def __init__(
        self,
        min_score: int | None = None,
        min_salary_max: int | None = None,
        max_salary_max: int | None = None,
        locations: list[str] | None = None,
        specializations: list[str] | None = None,
        max_experience_gap_years: float | None = None,
        allow_top_tier_companies: bool = False,
        excluded_companies: list[str] | None = None,
        employment_types: list[str] | None = None,
        work_formats: list[str] | None = None,
    ):
        self.min_score = min_score
        self.min_salary_max = min_salary_max
        self.max_salary_max = max_salary_max
        self.locations = [loc.lower().strip() for loc in (locations or []) if loc.strip()]
        self.specializations = [spec.upper().strip() for spec in (specializations or [])]
        self.max_experience_gap_years = max_experience_gap_years
        self.allow_top_tier_companies = allow_top_tier_companies
        self.excluded_companies = [
            c.lower().strip() for c in (excluded_companies or []) if c.strip()
        ]
        self.employment_types = [t.lower().strip() for t in (employment_types or []) if t.strip()]
        self.work_formats = [f.lower().strip() for f in (work_formats or []) if f.strip()]

    def evaluate(
        self,
        job: Job,
        match: MatchResult,
        profile: CandidateProfile,
    ) -> tuple[bool, list[str]]:
        """Return (permitted, reasons) for a given (job, match, profile) triple."""
        reasons: list[str] = []

        if self.min_score is not None and match.score < self.min_score:
            reasons.append(f"score {match.score} < policy min_score {self.min_score}")

        if job.salary_max is not None:
            if self.min_salary_max is not None and job.salary_max < self.min_salary_max:
                reasons.append(
                    f"salary_max {job.salary_max} < policy min_salary_max " f"{self.min_salary_max}"
                )
            if self.max_salary_max is not None and job.salary_max > self.max_salary_max:
                reasons.append(
                    f"salary_max {job.salary_max} > policy max_salary_max " f"{self.max_salary_max}"
                )

        if self.locations and job.location:
            if job.location.lower().strip() not in self.locations:
                reasons.append(f"location '{job.location}' not in policy locations")

        if self.specializations and (job.specializations or []):
            if not any(spec in self.specializations for spec in job.specializations):
                reasons.append(
                    f"job specializations {job.specializations} do not match "
                    f"policy {self.specializations}"
                )

        if self.excluded_companies and job.company:
            if job.company.lower().strip() in self.excluded_companies:
                reasons.append(f"company '{job.company}' is excluded by policy")

        if self.employment_types and job.employment_type:
            if job.employment_type.lower().strip() not in self.employment_types:
                reasons.append(f"employment_type '{job.employment_type}' not allowed by policy")

        if self.work_formats and job.work_format:
            if job.work_format.lower().strip() not in self.work_formats:
                reasons.append(f"work_format '{job.work_format}' not allowed by policy")

        if self.max_experience_gap_years is not None:
            gap = self._experience_gap(profile, job)
            if gap is not None and gap > self.max_experience_gap_years:
                reasons.append(
                    f"experience gap {gap:.1f}y exceeds policy max "
                    f"{self.max_experience_gap_years:.1f}y"
                )

        permitted = len(reasons) == 0
        if not permitted:
            logger.info(
                "Policy check for job %s: NOT_PERMITTED (%s)",
                getattr(job, "id", "?"),
                "; ".join(reasons),
            )
        return permitted, reasons

    @staticmethod
    def _experience_gap(profile: CandidateProfile, job: Job) -> float | None:
        """Return the gap in years (required - candidate) or None if undetermined."""
        if job.experience_required is None or profile.experience_years is None:
            return None
        return max(0.0, float(job.experience_required) - float(profile.experience_years))
