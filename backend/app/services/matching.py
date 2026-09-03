"""Job matching service for analyzing jobs against candidate profile."""

import re
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
from app.providers.ai.base import SkillMatch
from app.providers.ai.factory import create_ai_provider
from app.repositories.candidate import ResumeProfileRepository
from app.repositories.job import JobRepository
from app.repositories.matching import MatchResultRepository
from app.schemas.matching import (
    GapAnalysisResponse,
    GapItem,
    MatchResultResponse,
    SoftMatchResponse,
)
from app.schemas.resume import ResumeRecommendationResponse
from app.services.candidate import CandidateService
from app.services.hard_filters import HardFilterEngine
from app.services.llm_cache import CachedAIProvider
from app.services.resume_selection import ResumeSelector
from app.services.scoring import ScoringEngine
from app.services.skill_taxonomy import skill_variants
from app.services.specialization import classify_job
from app.services.stretch_classifier import StretchClassifier

logger = get_logger(__name__)

# matched_skills are stored in a TEXT[] column as human-readable strings
# ("SQL (exact, 1.0)"); plain "SQL" means exact/1.0. The AI provider returns
# SkillMatch objects, which are serialized on persist and parsed back for
# the API response (frontend contract: matched_skills: SkillMatch[]).
_SKILL_MATCH_RE = re.compile(r"^(?P<skill>.+?)\s*\((?P<type>\w+)(?:,\s*(?P<conf>[\d.]+))?\)$")


def serialize_skill_matches(skills: Any) -> list[str]:
    """Convert AI SkillMatch objects into TEXT[]-safe strings."""
    result: list[str] = []
    for item in skills or []:
        if isinstance(item, SkillMatch):
            if item.match_type == "exact" and item.confidence == 1.0:
                result.append(item.skill)
            elif item.confidence == 1.0:
                result.append(f"{item.skill} ({item.match_type})")
            else:
                result.append(f"{item.skill} ({item.match_type}, {item.confidence:g})")
        elif isinstance(item, str):
            result.append(item)
        else:
            result.append(str(item))
    return result


def parse_skill_match(raw: str) -> SkillMatch:
    """Restore a SkillMatch from its stored string form."""
    match = _SKILL_MATCH_RE.match((raw or "").strip())
    if not match:
        return SkillMatch(skill=(raw or "").strip())
    confidence = float(match.group("conf")) if match.group("conf") else 1.0
    return SkillMatch(
        skill=match.group("skill"),
        match_type=match.group("type"),
        confidence=confidence,
    )


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

    def _deterministic_skill_match(
        self, profile: CandidateProfile, job: Job
    ) -> tuple[list[str], list[str]]:
        """Return (matched_skills, missing_skills) using deterministic token matching."""
        job_text = f"{job.title} {job.description or ''}"
        job_tokens = self.scoring._tokenize_text(job_text)
        candidate_skills = set()
        candidate_skills.update(self.scoring._normalize_skills(profile.skills))
        candidate_skills.update(self.scoring._normalize_skills(profile.technologies))

        matched, missing = [], []
        for skill in candidate_skills:
            if skill in self.scoring.STOPWORDS and len(skill) < 4:
                continue
            variants = skill_variants(skill)
            if variants & job_tokens or self.scoring._tokenize_text(skill) & job_tokens:
                matched.append(skill)
            else:
                missing.append(skill)
        return matched, missing

    async def soft_match(self, job, profile) -> SoftMatchResponse:
        """
        Lightweight soft-match: compute score + breakdown WITHOUT persistence.

        Hard filters are still applied (NOT_ELIGIBLE on critical mismatch).
        Deterministic only (no LLM). Returns SoftMatchResponse.
        """
        hard_result = self.hard_filters.evaluate(profile, job)
        if not hard_result.passed:
            return SoftMatchResponse(
                score=0,
                recommendation="NOT_ELIGIBLE",
                score_breakdown={"hard_filter_failed": True, "failures": hard_result.failures},
                matched_skills=[],
                missing_skills=[],
            )

        final_score, breakdown_raw = self.scoring.calculate(profile, job)
        breakdown = breakdown_raw.to_dict() if hasattr(breakdown_raw, "to_dict") else dict(breakdown_raw)
        score = round(final_score)

        stretch = self.stretch_classifier.analyze(profile, job, score)
        recommendation = (
            "STRETCH" if stretch.is_stretch
            else self.scoring.get_recommendation(score)
        )

        matched, missing = self._deterministic_skill_match(profile, job)

        return SoftMatchResponse(
            score=score,
            recommendation=recommendation,
            score_breakdown=breakdown,
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

        ai_score = final_score
        ai_result = None
        ai_tokens = None
        ai_cost = None

        # Hard requirements first (task spec #8): a critical failure makes
        # the vacancy NOT_ELIGIBLE regardless of any score, and the LLM is
        # never consulted for ineligible vacancies (task spec #29).
        hard = self.hard_filters.evaluate(profile, job)
        breakdown_dict: dict = {**breakdown.to_dict()}

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
            recommendation = MatchCategory.NOT_ELIGIBLE
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
        det_matched, det_missing = self._deterministic_skill_match(profile, job)

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
