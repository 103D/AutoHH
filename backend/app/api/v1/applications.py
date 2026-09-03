"""API endpoints for application tracking."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import DuplicateError, NotFoundError, ValidationError
from app.repositories.application import (
    ApplicationRepository,
    ApplicationStatusHistoryRepository,
)
from app.repositories.candidate import CandidateRepository
from app.repositories.job import JobRepository
from app.repositories.matching import MatchResultRepository
from app.schemas.application import (
    ApplicationCreate,
    ApplicationResponse,
    ApplicationUpdate,
    PackageResponse,
    StatusHistoryResponse,
)
from app.services.application import ApplicationService
from app.services.application_package import ApplicationPackageService
from app.services.candidate import CandidateService

router = APIRouter(prefix="/applications", tags=["applications"])


def get_application_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ApplicationService:
    """Dependency for application service."""
    app_repo = ApplicationRepository(session)
    history_repo = ApplicationStatusHistoryRepository(session)
    job_repo = JobRepository(session)
    candidate_repo = CandidateRepository(session)
    candidate_service = CandidateService(candidate_repo)
    return ApplicationService(app_repo, history_repo, job_repo, candidate_service)


@router.get("/", response_model=list[ApplicationResponse])
async def list_applications(
    session: Annotated[AsyncSession, Depends(get_db)],
    candidate_profile_id: UUID | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
):
    """List applications with optional filters."""
    service = get_application_service(session)
    return await service.get_applications(
        candidate_profile_id=candidate_profile_id,
        status=status_filter,
        limit=limit,
    )


@router.post("/", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(
    app_in: ApplicationCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a new application."""
    service = get_application_service(session)
    try:
        return await service.create_application(app_in)
    except DuplicateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.get("/by-job/{job_id}", response_model=ApplicationResponse | None)
async def get_application_by_job(
    job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Get the default candidate's application for a job (or null)."""
    service = get_application_service(session)
    try:
        return await service.get_application_for_job(job_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.get("/statistics", response_model=dict)
async def get_statistics(
    session: Annotated[AsyncSession, Depends(get_db)],
    candidate_profile_id: UUID | None = Query(None),
):
    """Get application statistics."""
    service = get_application_service(session)
    return await service.get_statistics(candidate_profile_id)


@router.get("/{application_id}", response_model=ApplicationResponse)
async def get_application(
    application_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Get application by ID."""
    service = get_application_service(session)
    try:
        return await service.get_application(application_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.patch("/{application_id}", response_model=ApplicationResponse)
async def update_application(
    application_id: UUID,
    app_in: ApplicationUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Update application (e.g., change status)."""
    service = get_application_service(session)
    try:
        return await service.update_application(application_id, app_in)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


@router.get(
    "/{application_id}/history",
    response_model=list[StatusHistoryResponse],
)
async def get_status_history(
    application_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Get status change history for an application."""
    service = get_application_service(session)
    try:
        return await service.get_status_history(application_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.post("/{application_id}/prepare-package", response_model=PackageResponse)
async def prepare_package(
    application_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Generate the application package for a job.

    Adapts the original resume, writes a cover letter, validates both against
    hallucinations, computes the diff/improvement metrics and stores
    everything in the application (status -> PREPARED).
    """
    service = get_application_service(session)
    package_service = ApplicationPackageService(
        service,
        JobRepository(session),
        MatchResultRepository(session),
    )
    try:
        application = await package_service.build_package(application_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None

    return PackageResponse(**application.package_data, application_id=application.id)


@router.get("/{application_id}/package", response_model=PackageResponse | None)
async def get_package(
    application_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Get the previously generated application package (if any)."""
    service = get_application_service(session)
    try:
        application = await service.get_application(application_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None

    if not application.package_data:
        return None
    return PackageResponse(**application.package_data, application_id=application.id)
