from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

class CandidateProfileBase(BaseModel):
    """Base schema for candidate profile."""
    
    desired_positions: list[str] = Field(..., min_length=1)
    skills: list[str] = Field(..., min_length=1)
    technologies: dict[str, list[str]] = Field(default_factory=dict)
    
    experience_years: int | None = Field(None, ge=0)
    experience_level: str | None = Field(None, pattern="^(junior|middle|senior|lead)$")
    
    education: list[dict[str, Any]] | None = None
    
    languages: dict[str, str] = Field(default_factory=dict)
    
    location: str | None = None
    desired_salary_min: int | None = Field(None, ge=0)
    desired_salary_max: int | None = Field(None, ge=0)
    salary_currency: str = Field("KZT", pattern="^[A-Z]{3}$")
    employment_types: list[str] | None = None
    work_formats: list[str] | None = None
    relocation_possible: bool = False
    business_trips_acceptable: bool = True
    
    resume_versions: dict[str, Any] = Field(default_factory=dict)
    additional_preferences: dict[str, Any] | None = None

class CandidateProfileCreate(CandidateProfileBase):
    """Schema for creating candidate profile."""
    user_id: UUID

class CandidateProfileUpdate(BaseModel):
    """Schema for updating candidate profile."""
    
    desired_positions: list[str] | None = None
    skills: list[str] | None = None
    technologies: dict[str, list[str]] | None = None
    
    experience_years: int | None = None
    experience_level: str | None = None
    
    education: list[dict[str, Any]] | None = None
    
    languages: dict[str, str] | None = None
    
    location: str | None = None
    desired_salary_min: int | None = None
    desired_salary_max: int | None = None
    salary_currency: str | None = None
    employment_types: list[str] | None = None
    work_formats: list[str] | None = None
    relocation_possible: bool | None = None
    business_trips_acceptable: bool | None = None
    
    resume_versions: dict[str, Any] | None = None
    additional_preferences: dict[str, Any] | None = None

class CandidateProfileResponse(CandidateProfileBase):
    """Schema for candidate profile response."""
    
    id: UUID
    user_id: UUID
    
    model_config = {"from_attributes": True}