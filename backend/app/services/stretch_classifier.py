"""Stretch-vacancy classifier.

A "stretch" is a vacancy slightly above the candidate's current level: a
realistic target with roughly a 10% offer chance that drives career growth.
The classifier runs deterministically (regex + keyword analysis, no AI) and
returns signals (reasons) and disqualifiers (blockers).
"""

from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.models.candidate import CandidateProfile
from app.models.job import Job
from app.services.scoring import ScoringEngine
from app.utils.experience import extract_required_experience_years

logger = get_logger(__name__)

LEVEL_ORDER = {"junior": 0, "middle": 1, "senior": 2, "lead": 3}
ORDER_LEVEL = {v: k for k, v in LEVEL_ORDER.items()}

# Companies where a stretch application has a too-low offer probability
TOP_TIER_COMPANIES = [
    "google", "meta", "amazon", "apple", "netflix", "microsoft", "openai",
    "yandex", "ozon", "avito", "vk", "tinkoff", "sber", "wildberries",
]

# Known skill keywords used to detect skills mentioned in vacancy text
SKILL_KEYWORDS = [
    "sql", "postgresql", "mysql", "clickhouse", "python", "pandas", "numpy",
    "power bi", "powerbi", "tableau", "excel", "etl", "airflow", "dbt",
    "spark", "kafka", "docker", "git", "ab testing", "a/b тест",
    "machine learning", "jupyter", "looker", "superset", "metabase", "dax",
    "bi", "визуализаци", "dashboards",
]


@dataclass
class StretchAnalysis:
    """Result of stretch classification for a vacancy."""

    is_stretch: bool
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    missing_key_skills: list[str] = field(default_factory=list)
    required_experience_years: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_stretch": self.is_stretch,
            "reasons": self.reasons,
            "blockers": self.blockers,
            "missing_key_skills": self.missing_key_skills,
            "required_experience_years": self.required_experience_years,
        }

class StretchClassifier:
    """Deterministic stretch-vacancy classifier.

    Rules (all configurable via settings):
    - required experience within 0.8x-1.5x of candidate years
    - 1-3 missing key skills
    - at most +1 grade vs candidate level
    - salary at most +40% above desired max
    - never top-tier companies
    """

    def __init__(self, config: dict | None = None):
        config = config or {}
        self.min_factor = config.get(
            "experience_min_factor", settings.stretch_experience_min_factor
        )
        self.max_factor = config.get(
            "experience_max_factor", settings.stretch_experience_max_factor
        )
        self.max_missing_skills = config.get(
            "max_missing_skills", settings.stretch_max_missing_skills
        )
        self.salary_max_increase = config.get(
            "salary_max_increase", settings.stretch_salary_max_increase
        )
        self.scoring = ScoringEngine()

    def extract_required_experience(self, job: Job) -> int | None:
        """Extract required years of experience from the vacancy description."""
        return extract_required_experience_years(job.description)

    @staticmethod
    def _level_from_years(years: int | None) -> str:
        """Derive a level from years of experience (mirrors resume parser rules)."""
        if years is None:
            return "junior"
        if years >= 9:
            return "lead"
        if years >= 5:
            return "senior"
        if years >= 2:
            return "middle"
        return "junior"

    @staticmethod
    def _infer_job_level(job: Job) -> str | None:
        """Infer the job's level from its title."""
        text = job.title.lower()
        for level in ("lead", "senior", "middle", "junior"):
            if level in text:
                return level
        if "ведущий" in text:
            return "lead"
        if "старший" in text or "сеньор" in text:
            return "senior"
        return None

    def find_missing_key_skills(self, profile: CandidateProfile, job: Job) -> list[str]:
        """Find well-known skills mentioned in the vacancy but absent for the candidate."""
        candidate_skills = self.scoring._normalize_skills(profile.skills) | self.scoring._normalize_skills(profile.technologies)
        job_text = f"{job.title} {job.description}".lower()

        missing: list[str] = []
        for keyword in SKILL_KEYWORDS:
            if keyword not in job_text:
                continue
            # Candidate has it under a different form? (substring either way)
            if any(keyword in skill or skill in keyword for skill in candidate_skills):
                continue
            display = keyword.capitalize() if keyword.isalpha() else keyword.upper()
            missing.append(display)
        return missing

    def analyze(self, profile: CandidateProfile, job: Job, score: float) -> StretchAnalysis:
        """Classify a vacancy as a stretch opportunity for the candidate."""
        analysis = StretchAnalysis(
            is_stretch=False,
            required_experience_years=self.extract_required_experience(job),
        )
        reasons: list[str] = []
        blockers: list[str] = []

        # 1) Experience above current level but within 1.5x
        years = profile.experience_years
        required = analysis.required_experience_years
        if years is not None and required is not None and required > years:
            if required <= years * self.max_factor:
                reasons.append(f"Job requires {required}+ years vs candidate's {years}")
            else:
                blockers.append(f"Experience gap too large: {required}+ years vs {years}")

        # 2) Grade at most +1
        candidate_level = profile.experience_level or self._level_from_years(years)
        job_level = self._infer_job_level(job)
        if job_level and job_level in LEVEL_ORDER:
            delta = LEVEL_ORDER[job_level] - LEVEL_ORDER[candidate_level]
            if delta == 1:
                reasons.append(
                    f"Job level '{job_level}' is one grade above candidate's '{candidate_level}'"
                )
            elif delta > 1:
                blockers.append(
                    f"Job level '{job_level}' is more than one grade above '{candidate_level}'"
                )

        # 3) 1-3 missing key skills
        missing = self.find_missing_key_skills(profile, job)
        analysis.missing_key_skills = missing
        if 1 <= len(missing) <= self.max_missing_skills:
            reasons.append(f"Missing {len(missing)} key skill(s): {', '.join(missing)}")
        elif len(missing) > self.max_missing_skills:
            blockers.append(f"Too many missing key skills: {len(missing)}")

        # 4) Salary at most +40% above desired max
        if job.salary_max and profile.desired_salary_max:
            allowed = int(profile.desired_salary_max * (1 + self.salary_max_increase))
            if job.salary_max > profile.desired_salary_max:
                if job.salary_max <= allowed:
                    reasons.append(
                        "Salary above desired max but within "
                        f"+{int(self.salary_max_increase * 100)}% stretch allowance"
                    )
                else:
                    blockers.append(
                        f"Salary {job.salary_max} exceeds desired max "
                        f"+{int(self.salary_max_increase * 100)}% ({allowed})"
                    )

        # 5) Top-tier company blocker
        company_lower = job.company.lower()
        for tier in TOP_TIER_COMPANIES:
            if tier in company_lower:
                blockers.append(f"Top-tier company: {job.company}")
                break

        analysis.reasons = reasons
        analysis.blockers = blockers
        analysis.is_stretch = bool(reasons) and not blockers
        if analysis.is_stretch:
            logger.debug(f"Stretch opportunity: {job.title} ({job.company})")
        return analysis
