from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class JobSourceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    # type is the provider key consumed by create_job_provider (e.g. hh_kz, remote_ok),
    # not an abstract "api"/"scraper" category.

    type: str = Field(..., min_length=1, max_length=50)
    enabled: bool = True
    configuration: dict[str, Any] = Field(default_factory=dict)


class JobSourceCreate(JobSourceBase):
    pass


class JobSourceUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    enabled: bool | None = None
    configuration: dict[str, Any] | None = None


class JobSourceResponse(JobSourceBase):
    id: UUID
    last_fetch_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    fetch_count: int = 0
    error_count: int = 0
    consecutive_errors: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    company: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)

    location: str | None = None
    salary_min: int | None = Field(None, ge=0)
    salary_max: int | None = Field(None, ge=0)
    currency: str | None = Field(None, pattern="^[A-Z]{3}$")

    employment_type: str | None = None
    work_format: str | None = None
    experience_required: int | None = Field(None, ge=0)

    # Multi-label specialization (task spec #11); set by the normalizer
    specializations: list[str] | None = None

    url: str
    published_at: datetime | None = None

    @field_validator("salary_max")
    @classmethod
    def validate_salary_range(cls, v: int | None, info) -> int | None:
        salary_min = info.data.get("salary_min")
        if v is not None and salary_min is not None and v < salary_min:
            raise ValueError("salary_max must be greater than or equal to salary_min")
        return v


class JobCreate(JobBase):
    source_id: UUID
    external_id: str
    # Denormalized job_sources.type persisted on the Job row (task spec #7);
    # set by the ingestion pipeline, optional for manual creation paths.
    source_type: str | None = None
    raw_data: dict[str, Any] = Field(default_factory=dict)


class JobUpdate(BaseModel):
    title: str | None = None
    company: str | None = None
    description: str | None = None
    location: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    currency: str | None = None
    employment_type: str | None = None
    work_format: str | None = None
    experience_required: int | None = Field(None, ge=0)
    specializations: list[str] | None = None
    published_at: datetime | None = None

    @field_validator("salary_max")
    @classmethod
    def validate_salary_range(cls, v: int | None, info) -> int | None:
        salary_min = info.data.get("salary_min")
        if v is not None and salary_min is not None and v < salary_min:
            raise ValueError("salary_max must be greater than or equal to salary_min")
        return v


class JobResponse(JobBase):
    id: UUID
    source_id: UUID
    # Persisted denormalized source type (jobs.source_type); ``source`` is a
    # backward-compatible alias served by the model property.
    source_type: str | None = None
    source: str | None = None
    external_id: str

    first_seen_at: datetime
    last_seen_at: datetime

    content_hash: str
    url_normalized: str

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ManualJobCreate(BaseModel):
    """Manual job import payload (PROMPT.MD #4 — mandatory fallback).

    Only title/company/description are required; everything else is optional.
    The payload goes through the same normalization and dedup pipeline as
    every real provider; a stable external_id is derived from the content
    hash when not supplied, so repeated imports are idempotent.
    """

    title: str = Field(..., min_length=1, max_length=500)
    company: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)

    url: str | None = None
    location: str | None = None
    salary_min: int | None = Field(None, ge=0)
    salary_max: int | None = Field(None, ge=0)
    currency: str | None = Field(None, pattern="^[A-Z]{3}$")

    employment_type: str | None = None
    work_format: str | None = None
    experience_required: int | None = Field(None, ge=0)

    external_id: str | None = Field(None, max_length=255)
    published_at: datetime | None = None

    @field_validator("salary_max")
    @classmethod
    def validate_salary_range(cls, v: int | None, info) -> int | None:
        salary_min = info.data.get("salary_min")
        if v is not None and salary_min is not None and v < salary_min:
            raise ValueError("salary_max must be greater than or equal to salary_min")
        return v


class ManualJobImportResponse(BaseModel):
    """Result of a manual import: the created job, or the existing duplicate."""

    job: JobResponse
    status: str = Field(..., description="'created' or 'duplicate'")
    duplicate_of: UUID | None = Field(
        None, description="ID of the existing job when status == 'duplicate'"
    )


class JobFilter(BaseModel):
    """Filter parameters for job search."""

    company: str | None = None
    location: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    currency: str | None = None
    employment_type: str | None = None
    work_format: str | None = None
    search: str | None = None  # Full-text search in title/description
    published_after: datetime | None = None
    source: str | None = None  # Job source type (e.g.hh_kz, remote_ok, habr_career)


class RawJob(BaseModel):
    """Raw job data from external source before normalization."""

    external_id: str
    title: str
    company: str
    description: str
    url: str

    location: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    currency: str | None = None
    employment_type: str | None = None
    work_format: str | None = None
    experience_required: int | None = None
    published_at: datetime | None = None

    raw_data: dict[str, Any] = Field(default_factory=dict)
