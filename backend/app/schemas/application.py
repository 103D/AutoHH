"""Schemas for application tracking."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ApplicationBase(BaseModel):
    """Base schema for application."""

    cover_letter: str | None = None
    adapted_resume: str | None = None
    notes: str | None = None


class ApplicationCreate(ApplicationBase):
    """Schema for creating application."""

    job_id: UUID
    candidate_profile_id: UUID | None = None


class ApplicationUpdate(BaseModel):
    """Schema for updating application."""

    status: str | None = Field(
        None,
        description="v2: DISCOVERED, SAVED, PREPARED, MANUALLY_APPLIED, SKIPPED; "
        "legacy: DRAFT, READY, APPLIED, SCREENING, INTERVIEW, "
        "TECHNICAL_INTERVIEW, OFFER, REJECTED, WITHDRAWN, NO_RESPONSE",
    )
    cover_letter: str | None = None
    adapted_resume: str | None = None
    notes: str | None = None
    comment: str | None = Field(None, description="Comment for status change")

    # === Feedback loop outcomes (task spec #17) ===
    resume_profile_id: UUID | None = Field(
        None, description="Resume profile used for this application"
    )
    response_received_at: datetime | None = Field(
        None, description="When the employer first responded"
    )
    interview_stage: str | None = Field(
        None,
        description="Interview stage reached: screening, technical, final, offer",
    )
    rejection_reason: str | None = Field(None, description="Why the application was rejected")
    offer_salary_min: int | None = Field(None, ge=0)
    offer_salary_max: int | None = Field(None, ge=0)


class ApplicationResponse(ApplicationBase):
    """Schema for application response."""

    id: UUID
    job_id: UUID
    candidate_profile_id: UUID
    status: str
    applied_at: datetime | None = None
    resume_profile_id: UUID | None = None
    response_received_at: datetime | None = None
    interview_stage: str | None = None
    rejection_reason: str | None = None
    offer_salary_min: int | None = None
    offer_salary_max: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StatusHistoryResponse(BaseModel):
    """Schema for status history entry."""

    id: UUID
    application_id: UUID
    from_status: str | None
    to_status: str
    comment: str | None
    changed_at: datetime

    model_config = {"from_attributes": True}


class PackageDiff(BaseModel):
    """Diff between original and adapted resume."""

    added_lines: int = 0
    removed_lines: int = 0
    unified_diff: str = ""


class PackageResponse(BaseModel):
    """Generated application package (adapted resume + cover letter)."""

    application_id: UUID
    adapted_resume: str
    cover_letter: str
    diff: PackageDiff
    keyword_coverage: dict[str, float] = Field(
        default_factory=dict, description="Job-keyword coverage before/after adaptation"
    )
    improvement_score: float = Field(
        description="Coverage improvement in percentage points"
    )
    validation: dict = Field(default_factory=dict)
    generated_at: str
    ai_model: str | None = None


class ApplicationStatistics(BaseModel):
    """Schema for application statistics."""

    total: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    interview_rate: float = 0.0
    response_rate: float = 0.0
