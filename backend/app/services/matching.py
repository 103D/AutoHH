"""Job matching service for analyzing jobs against candidate profile."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.candidate import CandidateProfile
from app.models.job import Job
from app.models.matching import MatchCategory, MatchResult
from app.providers.ai.factory import create_ai_provider
from app.repositories.job import JobRepository
from app.repositories.matching import MatchResultRepository
from app.schemas.matching import GapAnalysisResponse, GapItem, MatchResultResponse
from app.services.candidate import CandidateService
from app.services.scoring import ScoringEngine
from app.services.stretch_classifier import StretchClassifier

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
        stretch_classifier: StretchClassifier | None = None,
    ):
        self.job_repository = job_repository
        self.candidate_service = candidate_service
        self.match_repository = match_repository
        self.ai_provider = ai_provider or create_ai_provider()
        self.scoring = scoring_engine or ScoringEngine()
        self.stretch_classifier = stretch_classifier or StretchClassifier()

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
            return self._to_response(existing)

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

        # Stretch classification (deterministic, no extra AI calls)
        stretch = self.stretch_classifier.analyze(profile, job, final_score)
        if stretch.is_stretch and recommendation in (
            MatchCategory.STRETCH,
            MatchCategory.SOLID_MATCH,
        ):
            recommendation = MatchCategory.STRETCH

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
            "score_breakdown": {**breakdown.to_dict(), "stretch": stretch.to_dict()},
            "ai_provider": settings.ai_provider if ai_result else None,
            "ai_model": settings.ai_model if ai_result else None,
            "ai_tokens_used": ai_tokens,
            "ai_cost_usd": ai_cost,
            "analyzed_at": now,
        }

        match_result = await self.match_repository.create(match_data)

        return self._to_response(match_result)

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
        return self._to_response(match)

    @staticmethod
    def effective_recommendation(match: MatchResult) -> str:
        """User override wins over the computed category."""
        return match.user_override_recommendation or match.recommendation

    def _to_response(self, match: MatchResult) -> MatchResultResponse:
        """Convert a MatchResult model into a response schema."""
        breakdown = match.score_breakdown or {}
        return MatchResultResponse(
            job_id=match.job_id,
            candidate_profile_id=match.candidate_profile_id,
            score=match.score,
            recommendation=match.recommendation,
            user_override_recommendation=match.user_override_recommendation,
            matched_skills=match.matched_skills,
            missing_skills=match.missing_skills,
            strong_matches=match.strong_matches,
            concerns=match.concerns,
            reasoning_summary=match.reasoning_summary or "",
            stretch_analysis=breakdown.get("stretch"),
            analyzed_at=match.analyzed_at,
        )

    async def set_recommendation_override(
        self,
        job_id: UUID,
        candidate_profile_id: UUID | None,
        category: str,
    ) -> MatchResultResponse:
        """Manually override the match category for a job."""
        profile_id = candidate_profile_id or (await self.get_default_candidate_profile()).id
        match = await self.match_repository.get_by_job_and_candidate(job_id, profile_id)
        if not match:
            raise NotFoundError(
                f"No match result for job {job_id}. Analyze the job first."
            )
        updated = await self.match_repository.update(
            match, {"user_override_recommendation": category}
        )
        logger.info(
            f"User override: job {job_id} -> {category} "
            f"(was {updated.recommendation})"
        )
        return self._to_response(updated)

    async def clear_recommendation_override(
        self,
        job_id: UUID,
        candidate_profile_id: UUID | None = None,
    ) -> MatchResultResponse:
        """Remove the manual category override."""
        profile_id = candidate_profile_id or (await self.get_default_candidate_profile()).id
        match = await self.match_repository.get_by_job_and_candidate(job_id, profile_id)
        if not match:
            raise NotFoundError(f"No match result for job {job_id}")
        updated = await self.match_repository.update(
            match, {"user_override_recommendation": None}
        )
        return self._to_response(updated)

    def _build_gaps(
        self,
        profile: CandidateProfile,
        job: Job,
        match: MatchResult,
    ) -> list[GapItem]:
        """Build the skill/experience gap list for a job."""
        gaps: list[GapItem] = []

        missing = list(match.missing_skills or [])
        if not missing:
            missing = self.stretch_classifier.find_missing_key_skills(profile, job)
        for skill in missing[:10]:
            gaps.append(GapItem(skill=skill, gap_type="missing", priority="high"))

        required_years = self.stretch_classifier.extract_required_experience(job)
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

    async def get_gap_analysis(
        self,
        job_id: UUID,
        candidate_profile_id: UUID | None = None,
    ) -> GapAnalysisResponse:
        """Return a skill-gap analysis for a specific job."""
        job = await self.job_repository.get(job_id)
        if not job:
            raise NotFoundError(f"Job {job_id} not found")

        if candidate_profile_id:
            profile = await self.candidate_service.get_profile(candidate_profile_id)
        else:
            profile = await self.get_default_candidate_profile()

        match = await self.match_repository.get_by_job_and_candidate(job_id, profile.id)
        if not match:
            raise NotFoundError(
                f"No match result for job {job_id}. Analyze the job first."
            )

        stretch = self.stretch_classifier.analyze(profile, job, match.score)
        gaps = self._build_gaps(profile, job, match)
        effective = self.effective_recommendation(match)

        summary = (
            f"Score {match.score} ({effective}). "
            f"{len(gaps)} gap(s) identified."
        )
        if stretch.is_stretch:
            summary += " Realistic stretch opportunity."

        return GapAnalysisResponse(
            job_id=job_id,
            candidate_profile_id=profile.id,
            score=match.score,
            recommendation=match.recommendation,
            effective_recommendation=effective,
            gaps=gaps,
            stretch_analysis=stretch.to_dict(),
            summary=summary,
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
