"""API endpoints for resume profile management (task specs #12, #16)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import DuplicateError, NotFoundError, ValidationError
from app.repositories.candidate import CandidateRepository, ResumeProfileRepository
from app.schemas.resume import ResumeProfileCreate, ResumeProfileResponse, ResumeProfileUpdate
from app.services.resume_profile import ResumeProfileService

router = APIRouter(tags=["resume-profiles"])


def get_resume_profile_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ResumeProfileService:
    """Dependency for resume profile service."""
    return ResumeProfileService(
        ResumeProfileRepository(session),
        CandidateRepository(session),
    )


@router.get(
    "/profile/{profile_id}/resume-profiles",
    response_model=list[ResumeProfileResponse],
)
async def list_resume_profiles(
    profile_id: UUID,
    service: Annotated[ResumeProfileService, Depends(get_resume_profile_service)],
):
    """List resume profiles of a candidate (one per specialization)."""
    try:
        return await service.list_profiles(profile_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.post(
    "/profile/{profile_id}/resume-profiles",
    response_model=ResumeProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_resume_profile(
    profile_id: UUID,
    data: ResumeProfileCreate,
    service: Annotated[ResumeProfileService, Depends(get_resume_profile_service)],
):
    """Create a specialized resume profile referencing master-profile facts."""
    try:
        return await service.create_profile(profile_id, data)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except DuplicateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


@router.get("/resume-profiles/{resume_profile_id}", response_model=ResumeProfileResponse)
async def get_resume_profile(
    resume_profile_id: UUID,
    service: Annotated[ResumeProfileService, Depends(get_resume_profile_service)],
):
    """Get one resume profile by ID."""
    try:
        return await service.get_profile(resume_profile_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.put("/resume-profiles/{resume_profile_id}", response_model=ResumeProfileResponse)
async def update_resume_profile(
    resume_profile_id: UUID,
    data: ResumeProfileUpdate,
    service: Annotated[ResumeProfileService, Depends(get_resume_profile_service)],
):
    """Update a resume profile (partial)."""
    try:
        return await service.update_profile(resume_profile_id, data)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


@router.delete(
    "/resume-profiles/{resume_profile_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_resume_profile(
    resume_profile_id: UUID,
    service: Annotated[ResumeProfileService, Depends(get_resume_profile_service)],
):
    """Delete a resume profile."""
    try:
        await service.delete_profile(resume_profile_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
