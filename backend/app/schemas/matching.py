"""Schemas for job matching results."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.providers.ai.base import SkillMatch


class MatchResultBase(BaseModel):
    """Base schema for match result."""

    score: int = Field(ge=0, le=100, description="Compatibility score")
    recommendation: str = Field(description="HIGH_PRIORITY, APPLY, REVIEW, or IGNORE")
    matched_skills: list[SkillMatch] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    strong_matches: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    reasoning_summary: str = Field(description="Explanation of the match")
    salary_match: bool | None = None
    location_match: bool | None = None
    experience_match: bool | None = None


class MatchResultResponse(MatchResultBase):
    """Schema for match result response."""

    job_id: UUID
    candidate_profile_id: UUID
    analyzed_at: datetime

    model_config = {"from_attributes": True}


class ResumeAdaptRequest(BaseModel):
    """Request for resume adaptation."""

    job_id: UUID
    resume_text: str = Field(..., min_length=50, description="Original resume text")


class CoverLetterRequest(BaseModel):
    """Request for cover letter generation."""

    job_id: UUID
    candidate_name: str = Field(..., min_length=1)
    style: str = Field(default="professional", pattern="^(professional|casual|enthusiastic)$")


class CoverLetterResponse(BaseModel):
    """Response with generated cover letter."""

    job_id: UUID
    cover_letter: str
    generated_at: datetime
    validation: dict | None = None

    model_config = {"from_attributes": True}
