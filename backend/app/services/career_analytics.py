"""Career analytics service: market overview, skill gaps and learning roadmap.

All computations are deterministic aggregations over existing match results
and vacancies — no extra AI calls.
"""

from collections import Counter
from statistics import mean
from uuid import UUID

from app.core.logging import get_logger
from app.models.matching import MatchCategory
from app.repositories.job import JobRepository
from app.repositories.matching import MatchResultRepository
from app.services.candidate import CandidateService
from app.services.stretch_classifier import StretchClassifier
from app.services.telegram_v2 import effective_category

logger = get_logger(__name__)

# Categories that represent the candidate's real targets
TARGET_CATEGORIES = [
    MatchCategory.DREAM_JOB,
    MatchCategory.STRETCH,
    MatchCategory.SOLID_MATCH,
]


class CareerAnalyticsService:
    """Aggregates match results into market insights."""

    def __init__(
        self,
        match_repo: MatchResultRepository,
        job_repo: JobRepository,
        candidate_service: CandidateService,
        stretch_classifier: StretchClassifier | None = None,
    ):
        self.match_repo = match_repo
        self.job_repo = job_repo
        self.candidate_service = candidate_service
        self.stretch_classifier = stretch_classifier or StretchClassifier()

    async def _load_pairs(self, candidate_profile_id: UUID | None = None):
        """Load the candidate profile and (match, job) pairs."""
        if candidate_profile_id:
            profile = await self.candidate_service.get_profile(candidate_profile_id)
        else:
            profile = await self._default_profile()

        matches = await self.match_repo.get_for_candidate(profile.id)
        pairs = []
        for match in matches:
            job = await self.job_repo.get(match.job_id)
            if job:
                pairs.append((match, job))
        return profile, pairs

    async def _default_profile(self):
        profiles = await self.candidate_service.repository.get_multi(0, 1)
        if not profiles:
            from app.core.exceptions import NotFoundError

            raise NotFoundError("No candidate profile found")
        return profiles[0]

    @staticmethod
    def _in_target_categories(match) -> bool:
        return effective_category(match) in TARGET_CATEGORIES

    def _demanded_skills(self, pairs) -> list[dict]:
        """Skills most often mentioned across target vacancies."""
        from app.services.stretch_classifier import SKILL_KEYWORDS

        counter: Counter = Counter()
        for match, job in pairs:
            if not self._in_target_categories(match):
                continue
            text = f"{job.title} {job.description}".lower()
            for keyword in SKILL_KEYWORDS:
                if keyword in text:
                    display = keyword.capitalize() if keyword.isalpha() else keyword.upper()
                    counter[display] += 1
        return [
            {"skill": skill, "count": count}
            for skill, count in counter.most_common(10)
        ]

    async def market_overview(self, candidate_profile_id: UUID | None = None) -> dict:
        """Aggregate market picture across analyzed vacancies."""
        profile, pairs = await self._load_pairs(candidate_profile_id)

        by_category: Counter = Counter(
            effective_category(match) for match, _job in pairs
        )
        company_counter: Counter = Counter(
            job.company
            for match, job in pairs
            if self._in_target_categories(match) and job.company
        )
        companies = [
            {"company": company, "count": count}
            for company, count in company_counter.most_common(5)
        ]

        salary_min = [
            job.salary_min for _match, job in pairs if job.salary_min
        ]
        salary_max = [
            job.salary_max for _match, job in pairs if job.salary_max
        ]
        salary = {
            "avg_min": round(mean(salary_min)) if salary_min else None,
            "avg_max": round(mean(salary_max)) if salary_max else None,
            "vacancies_with_salary": len(salary_min) + len(salary_max),
        }

        return {
            "candidate_profile_id": profile.id,
            "total_analyzed": len(pairs),
            "by_category": dict(by_category),
            "top_companies": companies,
            "demanded_skills": self._demanded_skills(pairs),
            "salary": salary,
        }

    async def skill_gap(self, candidate_profile_id: UUID | None = None) -> dict:
        """Aggregate missing-skill gaps across target vacancies."""
        profile, pairs = await self._load_pairs(candidate_profile_id)

        gap_counter: Counter = Counter()
        analyzed = 0
        for match, job in pairs:
            if not self._in_target_categories(match):
                continue
            analyzed += 1
            missing = list(match.missing_skills or [])
            if not missing:
                missing = self.stretch_classifier.find_missing_key_skills(profile, job)
            for skill in missing:
                gap_counter[str(skill)] += 1

        gaps = []
        for skill, count in gap_counter.most_common(15):
            if count >= 3:
                priority = "high"
            elif count >= 2:
                priority = "medium"
            else:
                priority = "low"
            gaps.append({"skill": skill, "in_jobs": count, "priority": priority})

        return {
            "candidate_profile_id": profile.id,
            "analyzed_vacancies": analyzed,
            "gaps": gaps,
        }

    async def learning_roadmap(self, candidate_profile_id: UUID | None = None) -> dict:
        """Ordered learning roadmap: skills to close stretch gaps first."""
        gap_data = await self.skill_gap(candidate_profile_id)

        steps = []
        for position, gap in enumerate(gap_data["gaps"][:8], 1):
            steps.append(
                {
                    "position": position,
                    "skill": gap["skill"],
                    "in_jobs": gap["in_jobs"],
                    "priority": gap["priority"],
                    "rationale": (
                        f"Требуется в {gap['in_jobs']} из "
                        f"{gap_data['analyzed_vacancies']} целевых вакансий"
                    ),
                }
            )

        return {
            "candidate_profile_id": gap_data["candidate_profile_id"],
            "steps": steps,
            "total": len(steps),
        }

    async def dream_jobs(self, candidate_profile_id: UUID | None = None) -> dict:
        """List dream jobs: computed DREAM_JOB category or user override."""
        profile, pairs = await self._load_pairs(candidate_profile_id)

        jobs = []
        for match, job in pairs:
            category = effective_category(match)
            if category != MatchCategory.DREAM_JOB:
                continue
            is_override = bool(match.user_override_recommendation)
            jobs.append(
                {
                    "job_id": job.id,
                    "match_id": match.id,
                    "title": job.title,
                    "company": job.company,
                    "url": job.url,
                    "score": match.score,
                    "category": category,
                    "is_override": is_override,
                    "salary": {
                        "min": job.salary_min,
                        "max": job.salary_max,
                        "currency": job.currency,
                    },
                }
            )
        jobs.sort(key=lambda item: item["score"], reverse=True)

        return {
            "candidate_profile_id": profile.id,
            "total": len(jobs),
            "jobs": jobs,
        }
