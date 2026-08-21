from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_candidate_service, get_db
from app.core.exceptions import DuplicateError, NotFoundError
from app.schemas.candidate import (
    CandidateProfileCreate,
    CandidateProfileResponse,
    CandidateProfileUpdate,
    ResumeVersionCreate,
    ResumeVersionResponse,
)

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/", response_model=CandidateProfileResponse)
async def get_profile(
    user_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Get candidate profile by user ID."""
    service = get_candidate_service(session)
    try:
        profile = await service.get_profile_by_user(user_id)
        return profile
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.get("/{profile_id}", response_model=CandidateProfileResponse)
async def get_profile_by_id(
    profile_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Get candidate profile by ID."""
    service = get_candidate_service(session)
    try:
        profile = await service.get_profile(profile_id)
        return profile
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.post("/", response_model=CandidateProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(
    profile_in: CandidateProfileCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Create new candidate profile."""
    service = get_candidate_service(session)
    try:
        profile = await service.create_profile(profile_in)
        return profile
    except DuplicateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None


@router.put("/{profile_id}", response_model=CandidateProfileResponse)
async def update_profile(
    profile_id: UUID,
    profile_in: CandidateProfileUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Update candidate profile."""
    service = get_candidate_service(session)
    try:
        profile = await service.update_profile(profile_id, profile_in)
        return profile
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete candidate profile."""
    service = get_candidate_service(session)
    try:
        await service.delete_profile(profile_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


# Resume version endpoints
@router.get("/{profile_id}/resumes", response_model=list[ResumeVersionResponse])
async def list_resume_versions(
    profile_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """List all resume versions for a candidate profile."""
    service = get_candidate_service(session)
    try:
        profile = await service.get_profile(profile_id)
        versions = []
        for name, content in (profile.resume_versions or {}).items():
            versions.append({"name": name, "content": str(content)})
        return versions
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.post("/{profile_id}/resumes", response_model=ResumeVersionResponse, status_code=status.HTTP_201_CREATED)
async def add_resume_version(
    profile_id: UUID,
    resume_in: ResumeVersionCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Add or update a resume version."""
    service = get_candidate_service(session)
    try:
        profile = await service.get_profile(profile_id)
        versions = profile.resume_versions or {}
        versions[resume_in.name] = resume_in.content
        await service.repository.update(profile, {"resume_versions": versions})
        return {"name": resume_in.name, "content": resume_in.content}
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.delete("/{profile_id}/resumes/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume_version(
    profile_id: UUID,
    name: str,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete a resume version."""
    service = get_candidate_service(session)
    try:
        profile = await service.get_profile(profile_id)
        versions = profile.resume_versions or {}
        if name not in versions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Resume version '{name}' not found",
            )
        del versions[name]
        await service.repository.update(profile, {"resume_versions": versions})
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
