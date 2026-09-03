"""API endpoints for career analytics (market overview, gaps, roadmap)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.repositories.candidate import CandidateRepository
from app.repositories.job import JobRepository
from app.repositories.matching import MatchResultRepository
from app.schemas.analytics import (
    DreamJobsResponse,
    LearningRoadmapResponse,
    MarketOverviewResponse,
    SkillGapResponse,
)
from app.services.candidate import CandidateService
from app.services.career_analytics import CareerAnalyticsService

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
