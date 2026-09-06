"""API endpoints for job matching and analysis."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import NotFoundError
from app.repositories.candidate import CandidateRepository
from app.repositories.job import JobRepository
from app.repositories.matching import MatchResultRepository
from app.schemas.matching import (
    CoverLetterRequest,
    CoverLetterResponse,
    GapAnalysisResponse,
    MatchResultResponse,
    RecommendationOverrideRequest,
    ResumeAdaptRequest,
    SoftMatchResponse,
)
from app.schemas.resume import ResumeRecommendationResponse
from app.services.candidate import CandidateService
from app.services.matching import MatchingService
from app.services.validation import AntiHallucinationValidator

router = APIRouter(prefix="/matching", tags=["matching"])


def get_matching_service(session: Annotated[AsyncSession, Depends(get_db)]) -> MatchingService:
    """Dependency for matching service."""
    job_repo = JobRepository(session)
    candidate_repo = CandidateRepository(session)
    match_repo = MatchResultRepository(session)
    candidate_service = CandidateService(candidate_repo)
    return MatchingService(job_repo, candidate_service, match_repo)


@router.post("/jobs/{job_id}/analyze", response_model=MatchResultResponse)
async def analyze_job(
    job_id: UUID,
    candidate_profile_id: UUID | None = None,
    service: Annotated[MatchingService, Depends(get_matching_service)] = None,
):
    """
    Analyze a job against candidate profile.

    Args:
        job_id: Job ID to analyze
        candidate_profile_id: Optional candidate profile ID (uses default if not provided)

    Returns:
        MatchResultResponse with analysis results
    """
    try:
        result = await service.analyze_job(job_id, candidate_profile_id)
        return result
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.post("/jobs/{job_id}/recommend-resume", response_model=ResumeRecommendationResponse)
async def recommend_resume(
    job_id: UUID,
    candidate_profile_id: UUID | None = None,
    service: Annotated[MatchingService, Depends(get_matching_service)] = None,
):
    """
    Recommend the best resume profile for a vacancy (task spec #16).

    Deterministic: vacancy specialization -> matching resume profile.
    Every recommendation comes with an explanation.
    """
    try:
        return await service.recommend_resume(job_id, candidate_profile_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.post("/analyze-pending", response_model=list[MatchResultResponse])
async def analyze_pending_jobs(
    limit: int = 10,
    candidate_profile_id: UUID | None = None,
    service: Annotated[MatchingService, Depends(get_matching_service)] = None,
):
    """
    Analyze jobs that haven't been analyzed yet.

    Args:
        limit: Maximum number of jobs to analyze (default: 10)
        candidate_profile_id: Optional candidate profile ID

    Returns:
        List of MatchResultResponse
    """
    results = await service.analyze_pending_jobs(limit, candidate_profile_id)
    return results


@router.post("/analyze", response_model=MatchResultResponse)
async def analyze_job_endpoint(
    job_id: UUID,
    candidate_profile_id: UUID | None = None,
    service: Annotated[MatchingService, Depends(get_matching_service)] = None,
):
    """
    Analyze a specific job against the (default or specified) candidate profile.

    Persists the MatchResult so it is available for gap analysis, resume
    recommendation, and application creation.
    """
    try:
        result = await service.analyze_job(job_id, candidate_profile_id)
        return result
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.post("/match", response_model=SoftMatchResponse)
async def soft_match_job(
    job_id: UUID,
    candidate_profile_id: UUID | None = None,
    service: Annotated[MatchingService, Depends(get_matching_service)] = None,
):
    """
    Lightweight soft-match: compute score + breakdown **without** persistence.

    Hard filters are still applied (NOT_ELIGIBLE on critical mismatch). LLM is
    gated behind the deterministic threshold. Useful for quick UI tooltips and
    batch previews.
    """
    profile = await service.candidate_service.resolve_profile(candidate_profile_id)
    job = await service.job_repository.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found")

    return await service.soft_match(job, profile)


@router.post("/resume/adapt", response_model=dict)
async def adapt_resume(
    request: ResumeAdaptRequest,
    service: Annotated[MatchingService, Depends(get_matching_service)] = None,
):
    """
    Adapt resume for a specific job.

    Args:
        request: ResumeAdaptRequest with job_id and resume_text

    Returns:
        Dict with adapted resume text
    """
    try:
        # Get job
        job = await service.job_repository.get(request.job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {request.job_id} not found",
            )

        # Get key requirements from job
        key_requirements = [
            job.title,
            *job.description.split("\n")[:5],  # First 5 lines as key requirements
        ]

        adapted_resume = await service.ai_provider.adapt_resume(
            resume_text=request.resume_text,
            job_title=job.title,
            job_description=job.description,
            key_requirements=key_requirements,
        )

        # Validate against hallucinations
        validator = AntiHallucinationValidator()
        validation = validator.validate_resume(
            original_resume=request.resume_text,
            adapted_resume=adapted_resume,
        )
        if not validation.is_valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "Generated resume contains unsupported claims",
                    "issues": validation.issues,
                },
            )

        return {
            "job_id": str(request.job_id),
            "adapted_resume": adapted_resume,
            "adapted_at": datetime.now(UTC).isoformat(),
            "validation": {
                "is_valid": validation.is_valid,
                "issues": validation.issues,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to adapt resume: {str(e)}",
        ) from None


@router.post("/cover-letter", response_model=CoverLetterResponse)
async def generate_cover_letter(
    request: CoverLetterRequest,
    service: Annotated[MatchingService, Depends(get_matching_service)] = None,
):
    """
    Generate cover letter for a job application.

    Args:
        request: CoverLetterRequest with job_id and candidate details

    Returns:
        CoverLetterResponse with generated cover letter
    """
    try:
        # Get job
        job = await service.job_repository.get(request.job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {request.job_id} not found",
            )

        # Get candidate profile for key matches
        profile = await service.get_default_candidate_profile()

        key_matches = [
            f"Position: {pos}" for pos in profile.desired_positions[:3]
        ] + [
            f"Skill: {skill}" for skill in profile.skills[:5]
        ]

        cover_letter = await service.ai_provider.generate_cover_letter(
            candidate_name=request.candidate_name,
            job_title=job.title,
            company_name=job.company,
            job_description=job.description,
            key_matches=key_matches,
            style=request.style,
        )

        # Validate against hallucinations
        validator = AntiHallucinationValidator()
        profile_dict = {
            "skills": profile.skills,
            "technologies": profile.technologies,
            "experience_years": profile.experience_years,
            "desired_positions": profile.desired_positions,
            "education": profile.education,
        }
        validation = validator.validate_cover_letter(profile_dict, cover_letter)

        return CoverLetterResponse(
            job_id=request.job_id,
            cover_letter=cover_letter,
            generated_at=datetime.now(UTC),
            validation={
                "is_valid": validation.is_valid,
                "issues": validation.issues,
            },
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate cover letter: {str(e)}",
        ) from None


@router.post("/resume/match", response_model=dict)
async def match_resume_to_job(
    request: ResumeAdaptRequest,
    service: Annotated[MatchingService, Depends(get_matching_service)] = None,
):
    """
    Match a resume against a specific job.

    Returns coverage percentage and matched/missing keywords.
    """
    try:
        result = await service.match_resume_to_job(
            resume_text=request.resume_text,
            job_id=request.job_id,
        )
        return result
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.get("/jobs/{job_id}/match", response_model=MatchResultResponse | None)
async def get_match_result(
    job_id: UUID,
    candidate_profile_id: UUID | None = None,
    service: Annotated[MatchingService, Depends(get_matching_service)] = None,
):
    """
    Get existing match result for a job.
    """
    if candidate_profile_id is None:
        profile = await service.get_default_candidate_profile()
        candidate_profile_id = profile.id

    result = await service.get_match_result(job_id, candidate_profile_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match result not found")
    return result


@router.put("/jobs/{job_id}/recommendation", response_model=MatchResultResponse)
async def override_recommendation(
    job_id: UUID,
    body: RecommendationOverrideRequest,
    candidate_profile_id: UUID | None = None,
    service: Annotated[MatchingService, Depends(get_matching_service)] = None,
):
    """
    Manually override the match category for a job.

    Useful for stretch jobs the user wants to promote to DREAM_JOB (or demote),
    independent of the computed score.
    """
    try:
        return await service.set_recommendation_override(
            job_id, candidate_profile_id, body.recommendation
        )
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.delete("/jobs/{job_id}/recommendation", response_model=MatchResultResponse)
async def clear_recommendation_override(
    job_id: UUID,
    candidate_profile_id: UUID | None = None,
    service: Annotated[MatchingService, Depends(get_matching_service)] = None,
):
    """
    Remove the manual match category override (fall back to the computed one).
    """
    try:
        return await service.clear_recommendation_override(job_id, candidate_profile_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.get("/jobs/{job_id}/gaps", response_model=GapAnalysisResponse)
async def get_gap_analysis(
    job_id: UUID,
    candidate_profile_id: UUID | None = None,
    service: Annotated[MatchingService, Depends(get_matching_service)] = None,
):
    """
    Get a skill/experience gap analysis for a job.

    Requires the job to be analyzed first (match result must exist).
    """
    try:
        return await service.get_gap_analysis(job_id, candidate_profile_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
