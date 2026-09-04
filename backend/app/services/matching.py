"""Job matching service — pipeline orchestration (match model v3).

MatchingService coordinates the pipeline and delegates domain logic to
focused modules:

    load job/profile -> deterministic scoring (app.services.scoring)
    -> hard filters (HardFilterEngine) -> LLM cost gate
    -> semantic merge (LLM requirements/equivalences re-run through the
       deterministic machinery) -> recommendation -> persist.

LLM boundary (match model v3): the LLM only extracts *semantics* (required
vs preferred skills, equivalents, transferable skills, explanation). It never
assigns a numeric score — the final number is purely deterministic.
"""

from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import UUID

from app.core import metrics
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.candidate import CandidateProfile
from app.models.job import Job
from app.models.matching import MatchCategory, MatchResult
from app.providers.ai.factory import create_ai_provider
from app.repositories.candidate import ResumeProfileRepository
from app.repositories.job import JobRepository
from app.repositories.matching import MatchResultRepository
from app.schemas.matching import (
    GapAnalysisResponse,
    MatchResultResponse,
    SoftMatchResponse,
)
from app.schemas.resume import ResumeRecommendationResponse
from app.services.candidate import CandidateService
from app.services.gap_analysis import build_gap_items
from app.services.hard_filters import HardFilterEngine
from app.services.llm_cache import CachedAIProvider
from app.services.resume_keyword_match import keyword_coverage
from app.services.resume_selection import ResumeSelector
from app.services.scoring import ScoringEngine
from app.services.scoring.skills import find_candidate_matches
from app.services.skill_match_codec import parse_skill_match, serialize_skill_matches
from app.services.specialization import classify_job
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
        hard_filters: HardFilterEngine | None = None,
        resume_profile_repository: ResumeProfileRepository | None = None,
        resume_selector: ResumeSelector | None = None,
    ):
        self.job_repository = job_repository
        self.candidate_service = candidate_service
        self.match_repository = match_repository
        self.scoring = scoring_engine or ScoringEngine()
        self.stretch_classifier = stretch_classifier or StretchClassifier()
        self.hard_filters = hard_filters or HardFilterEngine()

        # LLM result cache (task spec #28): drop-in decorator — same
        # analyze_job interface; no-ops when disabled or Redis is unavailable.
        provider = ai_provider or create_ai_provider()
        if settings.llm_cache_enabled:
            provider = CachedAIProvider(provider)
        self.ai_provider = provider
        self.resume_profile_repository = resume_profile_repository
        self.resume_selector = resume_selector or ResumeSelector()

    def _provider_name(self) -> str:
        """Provider label for metrics; the cache decorator forwards its name."""
        name = getattr(self.ai_provider, "name", None)
        return str(name) if name else self.ai_provider.__class__.__name__

    @staticmethod
    def _skill_lists(profile: CandidateProfile, job: Job) -> tuple[list[str], list[str]]:
        """Candidate-stack matches/misses against the vacancy text (display only)."""
        return find_candidate_matches(ScoringEngine.candidate_skills(profile), job)

    async def soft_match(self, job, profile) -> SoftMatchResponse:
        """
        Lightweight soft-match: compute score + breakdown WITHOUT persistence.

        Hard filters are still applied (NOT_ELIGIBLE on critical mismatch).
        Deterministic only (no LLM). Returns SoftMatchResponse with a full
        explainable breakdown (component scores + skill requirements audit).
        """
        hard_result = self.hard_filters.evaluate(profile, job)
        if not hard_result.passed:
            return SoftMatchResponse(
                score=0,
                recommendation="NOT_ELIGIBLE",
                score_breakdown={
                    "hard_filter_failed": True,
                    "failures": hard_result.failures,
                },
                matched_skills=[],
                missing_skills=[],
            )

        final_score, breakdown = self.scoring.calculate(profile, job)
        score = round(final_score)

        stretch = self.stretch_classifier.analyze(profile, job, score)
        recommendation = (
            "STRETCH"
            if stretch.is_stretch
            else self.scoring.get_recommendation(score)
        )

        matched, missing = self._skill_lists(profile, job)

        breakdown_dict = breakdown.to_full_dict()
        breakdown_dict["stretch"] = stretch.to_dict()

        return SoftMatchResponse(
            score=score,
            recommendation=recommendation,
            score_breakdown=breakdown_dict,
            matched_skills=matched,
            missing_skills=missing,
        )

    async def recommend_resume(
        self, job_id: UUID, candidate_profile_id: UUID | None = None
    ) -> ResumeRecommendationResponse:
        """Recommend the best resume profile for a vacancy (task spec #16).

        Deterministic pipeline: vacancy -> specializations -> resume profiles.
        """
        job = await self.job_repository.get(job_id)
        if not job:
            raise NotFoundError(f"Job {job_id} not found")

        profile = await self.candidate_service.resolve_profile(candidate_profile_id)

        # Ensure specializations exist (covers legacy vacancies)
        if getattr(job, "specializations", None) is None:
            job.specializations = classify_job(job.title, job.description)

        repository = self.resume_profile_repository
        if repository is None:
            # Lazy default reusing the candidate repository session
            repository = ResumeProfileRepository(self.candidate_service.repository.session)
        profiles = await repository.list_by_candidate(profile.id)

        return self.resume_selector.recommend(job, profiles)

    async def get_default_candidate_profile(self) -> CandidateProfile:
        """Get the first candidate profile (delegates to CandidateService)."""
        return await self.candidate_service.get_default_profile()

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

        profile = await self.candidate_service.resolve_profile(candidate_profile_id)

        existing = await self.match_repository.get_by_job_and_candidate(job_id, profile.id)
        if existing:
            logger.info(f"Job {job_id} already analyzed for profile {profile.id}, returning cached")
            return self._to_response(existing)

        final_score, breakdown = self.scoring.calculate(profile, job)

        # Multi-label specialization (task spec #11): classify once at
        # analysis time (also covers legacy rows created before this field
        # existed), persist, and reuse downstream (resume selection, UI).
        if getattr(job, "specializations", None) is None:
            specs = classify_job(job.title, job.description)
            try:
                await self.job_repository.update(job, {"specializations": specs})
            except Exception as e:  # classification is an optimization, never fatal
                logger.warning(f"Failed to persist specializations for job {job_id}: {e}")
            job.specializations = specs

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

        ai_result = None
        ai_tokens = None
        ai_cost = None

        # Hard requirements first (task spec #8): a critical failure makes
        # the vacancy NOT_ELIGIBLE regardless of any score, and the LLM is
        # never consulted for ineligible vacancies (task spec #29).
        hard = self.hard_filters.evaluate(profile, job)
        breakdown_dict = breakdown.to_full_dict()

        llm_allowed = hard.passed and (
            not settings.llm_gate_enabled
            or final_score >= settings.llm_gate_min_deterministic_score
        )

        analysis_outcome = "analyzed"
        analysis_started = perf_counter()

        if llm_allowed:
            try:
                ai_result = await self.ai_provider.analyze_job(
                    job_title=job.title,
                    job_company=job.company,
                    job_description=job.description,
                    job_requirements=job_requirements,
                    candidate_profile=profile_dict,
                )

                # LLM boundary (match model v3): the LLM supplies semantic
                # interpretation — requirements, importance, equivalents —
                # and the numeric score is re-computed deterministically.
                new_final, adjustments = self.scoring.apply_llm_requirements(
                    ai_result, profile, breakdown
                )
                if adjustments:
                    breakdown.llm_adjustments = adjustments
                if new_final is not None:
                    final_score = new_final
                breakdown_dict = breakdown.to_full_dict()
                ai_tokens = getattr(ai_result, "tokens_used", None)
                ai_cost = getattr(ai_result, "cost_usd", None)

            except Exception as e:
                logger.warning(
                    f"AI analysis failed for job {job_id}, using deterministic only: {e}"
                )
        elif not hard.passed:
            analysis_outcome = "hard_filtered"
            metrics.inc_llm(self._provider_name(), "hard_filtered")
            breakdown_dict["hard_failures"] = list(hard.failures)
            logger.info(f"Hard requirements failed for job {job_id}: {hard.failures}")
        else:
            analysis_outcome = "llm_skipped"
            metrics.inc_llm(self._provider_name(), "gate_skipped")
            breakdown_dict["llm_gate"] = {
                "skipped": True,
                "deterministic_score": final_score,
                "threshold": settings.llm_gate_min_deterministic_score,
            }
            logger.info(
                f"LLM gate: skipping AI for job {job_id} "
                f"(deterministic {final_score} < {settings.llm_gate_min_deterministic_score})"
            )

        metrics.observe_analysis(perf_counter() - analysis_started, analysis_outcome)

        if not hard.passed:
            # NOT_ELIGIBLE is assigned by hard filters, not by the score.
            # The persisted score is forced to 0 (consistent with soft_match).
            recommendation = MatchCategory.NOT_ELIGIBLE
            final_score = 0.0
        else:
            recommendation = self.scoring.get_recommendation(final_score)

        # Stretch classification (deterministic, no extra AI calls)
        stretch = self.stretch_classifier.analyze(profile, job, final_score)
        if (
            hard.passed
            and stretch.is_stretch
            and recommendation in (
                MatchCategory.STRETCH,
                MatchCategory.SOLID_MATCH,
            )
        ):
            recommendation = MatchCategory.STRETCH

        now = datetime.now(UTC).isoformat()

        # When AI didn't run, fall back to deterministic skill matching.
        det_matched, det_missing = self._skill_lists(profile, job)

        match_data = {
            "job_id": job_id,
            "candidate_profile_id": profile.id,
            "score": int(final_score),
            "recommendation": recommendation,
            "hard_failures": list(hard.failures),
            "matched_skills": serialize_skill_matches(
                ai_result.matched_skills if ai_result else det_matched
            ),
            "missing_skills": ai_result.missing_skills if ai_result else det_missing,
            "strong_matches": ai_result.strong_matches if ai_result else [],
            "concerns": ai_result.concerns if ai_result else [],
            "reasoning_summary": ai_result.reasoning_summary if ai_result else "Deterministic analysis only",
            "score_breakdown": {**breakdown_dict, "stretch": stretch.to_dict()},
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
        profile = await self.candidate_service.resolve_profile(candidate_profile_id)

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
            hard_failures=list(match.hard_failures or []),
            matched_skills=[
                parse_skill_match(s) for s in (match.matched_skills or [])
            ],
            missing_skills=match.missing_skills,
            strong_matches=match.strong_matches,
            concerns=match.concerns,
            reasoning_summary=match.reasoning_summary or "",
            score_breakdown=dict(breakdown),
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
        gaps = build_gap_items(profile, job, match, self.stretch_classifier)
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

        Delegates to the pure ``keyword_coverage`` helper
        (app.services.resume_keyword_match): no ORM, no AI.
        """
        job = await self.job_repository.get(job_id)
        if not job:
            raise NotFoundError(f"Job {job_id} not found")

        return keyword_coverage(resume_text, job)
