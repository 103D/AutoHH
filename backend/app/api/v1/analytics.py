"""API endpoints for career analytics (market overview, gaps, roadmap)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.repositories.application import ApplicationRepository
from app.repositories.candidate import CandidateRepository
from app.repositories.job import JobRepository
from app.repositories.matching import MatchResultRepository
from app.schemas.analytics import (
    DreamJobsResponse,
    FeedbackResponse,
    LearningRoadmapResponse,
    MarketOverviewResponse,
    SkillGapResponse,
)
from app.services.candidate import CandidateService
from app.services.career_analytics import CareerAnalyticsService
from app.services.feedback_analytics import FeedbackAnalyticsService
from app.services.threshold_advisor import ThresholdAdvisor, ThresholdSuggestion

router = APIRouter(prefix="/analytics", tags=["analytics"])


def get_analytics_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> CareerAnalyticsService:
    """Dependency for the career analytics service."""
    match_repo = MatchResultRepository(session)
    job_repo = JobRepository(session)
    candidate_service = CandidateService(CandidateRepository(session))
    return CareerAnalyticsService(match_repo, job_repo, candidate_service)


@router.get("/market-overview", response_model=MarketOverviewResponse)
async def market_overview(
    service: Annotated[CareerAnalyticsService, Depends(get_analytics_service)],
    candidate_profile_id: UUID | None = Query(None),
):
    """Aggregated market picture: categories, companies, demanded skills, salary."""
    return await service.market_overview(candidate_profile_id)


@router.get("/skill-gap", response_model=SkillGapResponse)
async def skill_gap(
    service: Annotated[CareerAnalyticsService, Depends(get_analytics_service)],
    candidate_profile_id: UUID | None = Query(None),
):
    """Aggregated skill gaps across the candidate's target vacancies."""
    return await service.skill_gap(candidate_profile_id)


@router.get("/learning-roadmap", response_model=LearningRoadmapResponse)
async def learning_roadmap(
    service: Annotated[CareerAnalyticsService, Depends(get_analytics_service)],
    candidate_profile_id: UUID | None = Query(None),
):
    """Ordered learning roadmap derived from stretch vacancies."""
    return await service.learning_roadmap(candidate_profile_id)


@router.get("/dream-jobs", response_model=DreamJobsResponse)
async def dream_jobs(
    service: Annotated[CareerAnalyticsService, Depends(get_analytics_service)],
    candidate_profile_id: UUID | None = Query(None),
):
    """List dream jobs (computed DREAM_JOB or user-overridden)."""
    return await service.dream_jobs(candidate_profile_id)


@router.get("/feedback", response_model=FeedbackResponse)
async def feedback_report(
    candidate_profile_id: UUID | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> FeedbackResponse:
    """Feedback-loop analytics: which scores/profiles/specializations convert
    to interviews, which missing skills correlate with rejections."""
    repo = ApplicationRepository(session)
    service = FeedbackAnalyticsService(repo)
    report = await service.feedback_report(candidate_profile_id)
    return FeedbackResponse(**report)


@router.get("/feedback/threshold-suggestions", response_model=ThresholdSuggestion)
async def threshold_suggestions(
    candidate_profile_id: UUID | None = Query(None),
    min_applications_per_bucket: int = Query(5, ge=1),
    session: AsyncSession = Depends(get_db),
) -> ThresholdSuggestion:
    """Adaptive threshold suggestions derived from feedback score buckets.

    Read-only advisor (spec #18/#32): runtime thresholds stay configuration —
    the response proposes values for LLM_GATE_MIN_DETERMINISTIC_SCORE and the
    skip-below score, it never changes behaviour automatically.
    """
    repo = ApplicationRepository(session)
    service = FeedbackAnalyticsService(repo)
    report = await service.feedback_report(candidate_profile_id)
    advisor = ThresholdAdvisor(min_applications_per_bucket=min_applications_per_bucket)
    return advisor.suggest_from_response(report)
