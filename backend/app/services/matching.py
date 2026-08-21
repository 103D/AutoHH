"""Job matching service for analyzing jobs against candidate profile."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.candidate import CandidateProfile
from app.providers.ai.factory import create_ai_provider
from app.repositories.job import JobRepository
from app.repositories.matching import MatchResultRepository
from app.schemas.matching import MatchResultResponse
from app.services.candidate import CandidateService
from app.services.scoring import ScoringEngine

logger = get_logger(__name__)


class MatchingService:
    """Service for job matching and analysis."""

    def __init__(
        self,
        job_repository: JobRepository,
        candidate_service: CandidateService,
        match_repository: MatchResultRepository,
        ai_provider: Any = None,
        scoring_engine: ScoringEngine = None,
    ):
        self.job_repository = job_repository
        self.candidate_service = candidate_service
        self.match_repository = match_repository
        self.ai_provider = ai_provider or create_ai_provider()
        self.scoring = scoring_engine or ScoringEngine()

    async def get_default_candidate_profile(self) -> CandidateProfile:
        """Get the first candidate profile (assumes single user for now)."""
        profiles = await self.candidate_service.repository.get_multi(0, 1)
        if not profiles:
            raise NotFoundError("No candidate profile found. Please create a profile first.")
        return profiles[0]

    async def analyze_job(
        self,
        job_id: UUID,
        candidate_profile_id: UUID | None = None,
    ) -> MatchResultResponse:
        """
        Analyze a job against candidate profile using hybrid scoring.
        """
        job = await self.job_repository.get(job_id)
        if not job:
            raise NotFoundError(f"Job {job_id} not found")

        if candidate_profile_id:
            profile = await self.candidate_service.get_profile(candidate_profile_id)
        else:
            profile = await self.get_default_candidate_profile()

        existing = await self.match_repository.get_by_job_and_candidate(job_id, profile.id)
        if existing:
            logger.info(f"Job {job_id} already analyzed for profile {profile.id}, returning cached")
            return MatchResultResponse(
                job_id=existing.job_id,
                candidate_profile_id=existing.candidate_profile_id,
                score=existing.score,
                recommendation=existing.recommendation,
                matched_skills=existing.matched_skills,
                missing_skills=existing.missing_skills,
                strong_matches=existing.strong_matches,
                concerns=existing.concerns,
                reasoning_summary=existing.reasoning_summary,
                analyzed_at=existing.analyzed_at,
            )

        final_score, breakdown = self.scoring.calculate(profile, job)

        job_requirements = {
            "location": job.location,
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "currency": job.currency,
            "employment_type": job.employment_type,
            "work_format": job.work_format,
        }

        profile_dict = {
            "desired_positions": profile.desired_positions,
            "skills": profile.skills,
            "technologies": profile.technologies,
            "experience_years": profile.experience_years,
            "location": profile.location,
            "desired_salary_min": profile.desired_salary_min,
            "desired_salary_max": profile.desired_salary_max,
            "salary_currency": profile.salary_currency,
            "employment_types": profile.employment_types,
            "work_formats": profile.work_formats,
            "relocation_possible": profile.relocation_possible,
            "business_trips_acceptable": profile.business_trips_acceptable,
            "languages": profile.languages,
        }

        ai_score = final_score
        ai_result = None
        ai_tokens = None
        ai_cost = None

        try:
            ai_result = await self.ai_provider.analyze_job(
                job_title=job.title,
                job_company=job.company,
                job_description=job.description,
                job_requirements=job_requirements,
                candidate_profile=profile_dict,
            )

            ai_score = ai_result.score
            final_score = round(
                final_score * (1 - settings.score_weight_semantic) +
                ai_score * settings.score_weight_semantic,
                1
            )
            ai_tokens = getattr(ai_result, 'tokens_used', None)
            ai_cost = getattr(ai_result, 'cost_usd', None)

        except Exception as e:
            logger.warning(f"AI analysis failed for job {job_id}, using deterministic only: {e}")

        recommendation = self.scoring.get_recommendation(final_score)

        now = datetime.now(UTC).isoformat()

        match_data = {
            "job_id": job_id,
            "candidate_profile_id": profile.id,
            "score": int(final_score),
            "recommendation": recommendation,
            "matched_skills": ai_result.matched_skills if ai_result else [],
            "missing_skills": ai_result.missing_skills if ai_result else [],
            "strong_matches": ai_result.strong_matches if ai_result else [],
            "concerns": ai_result.concerns if ai_result else [],
            "reasoning_summary": ai_result.reasoning_summary if ai_result else "Deterministic analysis only",
            "score_breakdown": breakdown.to_dict(),
            "ai_provider": settings.ai_provider if ai_result else None,
            "ai_model": settings.ai_model if ai_result else None,
            "ai_tokens_used": ai_tokens,
            "ai_cost_usd": ai_cost,
            "analyzed_at": now,
        }

        match_result = await self.match_repository.create(match_data)

        return MatchResultResponse(
            job_id=match_result.job_id,
            candidate_profile_id=match_result.candidate_profile_id,
            score=match_result.score,
            recommendation=match_result.recommendation,
            matched_skills=match_result.matched_skills,
            missing_skills=match_result.missing_skills,
            strong_matches=match_result.strong_matches,
            concerns=match_result.concerns,
            reasoning_summary=match_result.reasoning_summary,
            analyzed_at=match_result.analyzed_at,
        )

    async def analyze_pending_jobs(
        self,
        limit: int = 50,
        candidate_profile_id: UUID | None = None,
    ) -> list[MatchResultResponse]:
        if candidate_profile_id:
            profile = await self.candidate_service.get_profile(candidate_profile_id)
        else:
            profile = await self.get_default_candidate_profile()

        jobs = await self.job_repository.get_multi(0, limit)
        results = []
        for job in jobs:
            existing = await self.match_repository.get_by_job_and_candidate(job.id, profile.id)
            if existing:
                continue
            try:
                result = await self.analyze_job(job.id, profile.id)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to analyze job {job.id}: {e}")
                continue
        return results

    async def get_match_result(
        self,
        job_id: UUID,
        candidate_profile_id: UUID,
    ) -> MatchResultResponse | None:
        match = await self.match_repository.get_by_job_and_candidate(job_id, candidate_profile_id)
        if not match:
            return None
        return MatchResultResponse(
            job_id=match.job_id,
            candidate_profile_id=match.candidate_profile_id,
            score=match.score,
            recommendation=match.recommendation,
            matched_skills=match.matched_skills,
            missing_skills=match.missing_skills,
            strong_matches=match.strong_matches,
            concerns=match.concerns,
            reasoning_summary=match.reasoning_summary,
            analyzed_at=match.analyzed_at,
        )

    async def match_resume_to_job(
        self,
        resume_text: str,
        job_id: UUID,
    ) -> dict:
        """
        Match a specific resume version against a job.

        Args:
            resume_text: Resume text content
            job_id: Job ID to match against

        Returns:
            Dict with coverage percentage, matched and missing keywords
        """
        job = await self.job_repository.get(job_id)
        if not job:
            raise NotFoundError(f"Job {job_id} not found")

        # Extract keywords from resume
        resume_tokens = self.scoring._tokenize_text(resume_text)

        # Extract keywords from job
        job_text = f"{job.title} {job.description}"
        job_tokens = self.scoring._tokenize_text(job_text)

        # Find overlap
        matched = resume_tokens & job_tokens
        missing = job_tokens - resume_tokens

        # Filter to meaningful tokens (length > 2, not common words)
        common_words = {
            "the", "and", "for", "with", "you", "are", "our", "your", "this",
            "that", "from", "have", "will", "can", "not", "but", "all", "any",
            "who", "what", "when", "how", "why", "was", "were", "been", "being",
            "their", "there", "them", "then", "than", "into", "out", "about",
            "they", "she", "him", "her", "his", "its", "one", "two", "new",
            "use", "used", "using", "get", "got", "put", "set", "let",
        }
        meaningful_matched = {t for t in matched if len(t) > 2 and t not in common_words}
        meaningful_missing = {t for t in missing if len(t) > 2 and t not in common_words}

        total = len(meaningful_matched) + len(meaningful_missing)
        coverage = round(len(meaningful_matched) / total * 100, 1) if total > 0 else 0.0

        return {
            "job_id": str(job_id),
            "job_title": job.title,
            "coverage_pct": coverage,
            "matched_keywords": sorted(meaningful_matched),
            "missing_keywords": sorted(meaningful_missing),
        }
