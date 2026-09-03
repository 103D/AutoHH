"""Hard requirements filtering (task spec #8).

A critically unmet objective requirement (experience, work format,
location, employment type, salary floor) makes a vacancy NOT_ELIGIBLE
instead of merely producing a low score. MISSING skills do NOT belong
here — they are skill gaps, not disqualifiers.
"""

from dataclasses import dataclass, field

from app.core.config import settings
from app.models.candidate import CandidateProfile
from app.models.job import Job


@dataclass
class HardFilterResult:
    """Outcome of hard requirement evaluation."""

    passed: bool = True
    failures: list[str] = field(default_factory=list)

    def fail(self, requirement: str, detail: str) -> None:
        self.passed = False
        self.failures.append(f"{requirement}: {detail}")


# Minimal city alias map so "Алматы" == "almaty" and similar.
_CITY_ALIASES: dict[str, str] = {
    "almaty": "алматы",
    "alma-ata": "алматы",
    "алмата": "алматы",
    "astana": "астана",
    "nur-sultan": "астана",
    "нур-султан": "астана",
    "moscow": "москва",
    "мск": "москва",
    "saint petersburg": "санкт-петербург",
    "spb": "санкт-петербург",
    "питер": "санкт-петербург",
    "karaganda": "караганда",
    "shymkent": "шимкент",
    "chimkent": "шимкент",
    "tashkent": "ташкент",
}


def _normalize_city(city: str | None) -> str | None:
    if not city:
        return None
    key = city.strip().lower()
    return _CITY_ALIASES.get(key, key)


class HardFilterEngine:
    """Evaluates objective hard requirements; any failure => NOT_ELIGIBLE.

    All checks are skip-tolerant: when the candidate or the vacancy does
    not provide data for a check, the check passes (no fabricated limits).
    """

    def evaluate(self, profile: CandidateProfile, job: Job) -> HardFilterResult:
        result = HardFilterResult()
        if not settings.hard_filters_enabled:
            return result

        self._check_experience(profile, job, result)
        self._check_work_format(profile, job, result)
        self._check_location(profile, job, result)
        self._check_employment_type(profile, job, result)
        self._check_salary(profile, job, result)
        return result

    def _check_experience(
        self, profile: CandidateProfile, job: Job, result: HardFilterResult
    ) -> None:
        required = getattr(job, "experience_required", None)
        years = profile.experience_years
        if required is None or years is None:
            return
        max_allowed = years * settings.hard_experience_max_factor
        if required > max_allowed:
            result.fail(
                "experience",
                f"vacancy requires {required}+ years, candidate has {years}",
            )

    def _check_work_format(
        self, profile: CandidateProfile, job: Job, result: HardFilterResult
    ) -> None:
        job_fmt = (job.work_format or "").strip().lower()
        accepted = [f.strip().lower() for f in (profile.work_formats or []) if f]
        if not job_fmt or not accepted or job_fmt in accepted:
            return
        # An office-only vacancy for a candidate who never works on-site is
        # critical; hybrid/remote mismatches stay soft (common in listings).
        if job_fmt == "office" and "office" not in accepted:
            result.fail(
                "work_format",
                f"vacancy is office-only, candidate accepts: {', '.join(accepted)}",
            )
        elif job_fmt == "remote" and not ({"remote", "hybrid"} & set(accepted)):
            result.fail(
                "work_format",
                f"vacancy is remote, candidate accepts: {', '.join(accepted)}",
            )

    def _check_location(
        self, profile: CandidateProfile, job: Job, result: HardFilterResult
    ) -> None:
        cand_city = _normalize_city(profile.location)
        job_city = _normalize_city(job.location)
        if not cand_city or not job_city:
            return
        if job_city == cand_city or profile.relocation_possible:
            return
        if (job.work_format or "").strip().lower() == "remote":
            return
        result.fail(
            "location",
            f"vacancy is in '{job.location}', candidate is in "
            f"'{profile.location}', relocation not possible",
        )

    def _check_employment_type(
        self, profile: CandidateProfile, job: Job, result: HardFilterResult
    ) -> None:
        job_type = (job.employment_type or "").strip().lower()
        accepted = [t.strip().lower() for t in (profile.employment_types or []) if t]
        if not job_type or not accepted or job_type in accepted:
            return
        result.fail(
            "employment_type",
            f"vacancy is '{job.employment_type}', candidate accepts: "
            f"{', '.join(profile.employment_types or [])}",
        )

    def _check_salary(
        self, profile: CandidateProfile, job: Job, result: HardFilterResult
    ) -> None:
        if job.salary_max is None or profile.desired_salary_min is None:
            return
        # Different currencies cannot be compared deterministically.
        if (
            job.currency
            and profile.salary_currency
            and job.currency.upper() != profile.salary_currency.upper()
        ):
            return
        floor = profile.desired_salary_min * (1 - settings.hard_salary_tolerance)
        if job.salary_max < floor:
            result.fail(
                "salary",
                f"vacancy max {job.salary_max} {job.currency or ''} is below "
                f"candidate floor {profile.desired_salary_min} "
                f"{profile.salary_currency}",
            )
