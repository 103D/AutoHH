from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

class JobSourceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., pattern="^(api|scraper)$")
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
    
    url: str
    published_at: datetime | None = None

class JobCreate(JobBase):
    source_id: UUID
    external_id: str
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
    published_at: datetime | None = None

class JobResponse(JobBase):
    id: UUID
    source_id: UUID
    external_id: str
    
    first_seen_at: datetime
    last_seen_at: datetime
    
    content_hash: str
    url_normalized: str
    
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}

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
    published_at: datetime | None = None
    
    raw_data: dict[str, Any] = Field(default_factory=dict)