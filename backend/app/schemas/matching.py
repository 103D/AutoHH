"""Schemas for job matching results."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.matching import MatchCategory
from app.providers.ai.base import SkillMatch

RECOMMENDATION_CATEGORIES = MatchCategory.ALL


class MatchResultBase(BaseModel):
    """Base schema for match result."""

    score: int = Field(ge=0, le=100, description="Compatibility score")
    recommendation: str = Field(
        description=f"One of: {', '.join(RECOMMENDATION_CATEGORIES)}"
    )
    user_override_recommendation: str | None = Field(
        default=None, description="Manual category override set by the user"
    )
    hard_failures: list[str] = Field(
        default_factory=list,
        description="Hard requirement failures; non-empty means NOT_ELIGIBLE",
    )
    matched_skills: list[SkillMatch] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    strong_matches: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    reasoning_summary: str = Field(description="Explanation of the match")
    stretch_analysis: dict | None = Field(
        default=None, description="Stretch-vacancy classification details"
    )
    salary_match: bool | None = None
    location_match: bool | None = None
    experience_match: bool | None = None


class SoftMatchResponse(BaseModel):
    """Lightweight soft-match: component scores without persistence (spec #5)."""

    score: int = Field(ge=0, le=100)
    recommendation: str
    score_breakdown: dict = Field(default_factory=dict)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)


class RecommendationOverrideRequest(BaseModel):
    """Request to manually override the match category."""

    recommendation: str = Field(
        ...,
        description=f"One of: {', '.join(RECOMMENDATION_CATEGORIES)}",
    )

    @field_validator("recommendation")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in RECOMMENDATION_CATEGORIES:
            raise ValueError(
                f"recommendation must be one of: {', '.join(RECOMMENDATION_CATEGORIES)}"
            )
        return v


class GapItem(BaseModel):
    """A single skill/experience gap for a vacancy."""

    skill: str
    gap_type: str = Field(description="missing | partial | experience")
    priority: str = Field(description="high | medium | low")


class GapAnalysisResponse(BaseModel):
    """Skill-gap analysis for a specific vacancy."""

    job_id: UUID
    candidate_profile_id: UUID
    score: int
    recommendation: str
    effective_recommendation: str = Field(
        description="User override if set, otherwise the computed category"
    )
    gaps: list[GapItem] = Field(default_factory=list)
    stretch_analysis: dict | None = None
    summary: str


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
