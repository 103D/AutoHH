from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import NotFoundError
from app.repositories.job import JobRepository, JobSourceRepository
from app.schemas.job import (
    JobFilter,
    JobResponse,
    JobSourceCreate,
    JobSourceResponse,
    JobSourceUpdate,
)
from app.services.job import JobService, JobSourceService

router = APIRouter(prefix="/jobs", tags=["jobs"])


# Job endpoints
@router.get("/", response_model=list[JobResponse])
async def list_jobs(
    session: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    company: str | None = Query(None, description="Filter by company name (partial match)"),
    location: str | None = Query(None, description="Filter by location (partial match)"),
    salary_min: int | None = Query(None, ge=0, description="Minimum salary"),
    salary_max: int | None = Query(None, ge=0, description="Maximum salary"),
    currency: str | None = Query(
        None, min_length=3, max_length=3, description="Currency code (e.g., KZT, USD)"
    ),
    employment_type: str | None = Query(None, description="Employment type filter"),
    work_format: str | None = Query(None, description="Work format filter (e.g., remote, hybrid)"),
    search: str | None = Query(None, description="Full-text search in title and description"),
    published_after: datetime | None = Query(
        None, description="Filter jobs published after this date"
    ),
):
    """List all jobs with pagination and filters."""
    repo = JobRepository(session)
    service = JobService(repo)

    # Build filter object
    filters = JobFilter(
        company=company,
        location=location,
        salary_min=salary_min,
        salary_max=salary_max,
        currency=currency,
        employment_type=employment_type,
        work_format=work_format,
        search=search,
        published_after=published_after,
    )

    # Check if any filter is set
    has_filters = any(
        v is not None
        for v in [
            company,
            location,
            salary_min,
            salary_max,
            currency,
            employment_type,
            work_format,
            search,
            published_after,
        ]
    )

    return await service.get_jobs(skip, limit, filters if has_filters else None)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Get job by ID."""
    repo = JobRepository(session)
    service = JobService(repo)
    try:
        return await service.get_job(job_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


# Job Source endpoints
source_router = APIRouter(prefix="/sources", tags=["job-sources"])


@source_router.get("/", response_model=list[JobSourceResponse])
async def list_sources(
    session: Annotated[AsyncSession, Depends(get_db)],
    enabled_only: bool = Query(False),
):
    """List all job sources."""
    repo = JobSourceRepository(session)
    service = JobSourceService(repo)
    if enabled_only:
        return await service.get_enabled_sources()
    return await repo.get_multi()


@source_router.get("/{source_id}", response_model=JobSourceResponse)
async def get_source(
    source_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Get job source by ID."""
    repo = JobSourceRepository(session)
    service = JobSourceService(repo)
    try:
        return await service.get_source(source_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@source_router.post("/", response_model=JobSourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    source_in: JobSourceCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Create new job source."""
    repo = JobSourceRepository(session)
    service = JobSourceService(repo)
    try:
        return await service.create_source(source_in)
    except Exception as e:
        if "already exists" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
        raise


@source_router.put("/{source_id}", response_model=JobSourceResponse)
async def update_source(
    source_id: UUID,
    source_in: JobSourceUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Update job source."""
    repo = JobSourceRepository(session)
    service = JobSourceService(repo)
    try:
        source = await service.get_source(source_id)
        return await repo.update(source, source_in.model_dump(exclude_unset=True))
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@source_router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete job source."""
    repo = JobSourceRepository(session)
    source = await repo.get(source_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Source {source_id} not found"
        )
    await repo.delete(source_id)
