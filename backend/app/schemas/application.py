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
        description="DRAFT, READY, APPLIED, SCREENING, INTERVIEW, "
        "TECHNICAL_INTERVIEW, OFFER, REJECTED, WITHDRAWN, NO_RESPONSE",
    )
    cover_letter: str | None = None
    adapted_resume: str | None = None
    notes: str | None = None
    comment: str | None = Field(None, description="Comment for status change")


class ApplicationResponse(ApplicationBase):
    """Schema for application response."""

    id: UUID
    job_id: UUID
    candidate_profile_id: UUID
    status: str
    applied_at: datetime | None = None
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


class ApplicationStatistics(BaseModel):
    """Schema for application statistics."""

    total: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    interview_rate: float = 0.0
    response_rate: float = 0.0
