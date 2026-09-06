"""Schemas for the resume profile system (task specs #12, #13, #16)."""

from uuid import UUID

from pydantic import BaseModel, Field

from app.services.specialization import Specialization

SPECIALIZATION_PATTERN = "^(" + "|".join(Specialization.ALL) + ")$"


# === Master candidate profile structured facts (task spec #13) ===


class SkillMetadata(BaseModel):
    """Metadata for one skill in the master profile. No invented values."""

    category: str | None = Field(None, description="e.g. database, BI, programming")
    confidence: float | None = Field(None, ge=0, le=1)
    experience_level: str | None = Field(None, pattern="^(junior|middle|senior|lead)$")
    production_experience: bool | None = None
    years: float | None = Field(None, ge=0)


class ExperienceEntry(BaseModel):
    """Structured work-experience entry; ``id`` is referenced by ResumeProfiles."""

    id: str = Field(..., min_length=1)
    company: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    period_start: str | None = None
    period_end: str | None = None
    description: str | None = None
    achievements: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)


class ProjectEntry(BaseModel):
    """Structured project entry; ``id`` is referenced by ResumeProfiles."""

    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    role: str | None = None
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)
    results: list[str] = Field(default_factory=list)


class CertificationEntry(BaseModel):
    name: str = Field(..., min_length=1)
    issuer: str | None = None
    year: int | None = Field(None, ge=1900, le=2100)
    url: str | None = None


# === Resume profiles (task spec #12) ===


class ResumeProfileBase(BaseModel):
    specialization: str = Field(..., pattern=SPECIALIZATION_PATTERN)
    profile_name: str = Field(..., min_length=1, max_length=100)
    headline: str | None = None
    summary: str | None = None
    selected_skills: list[str] = Field(default_factory=list)
    selected_experience_ids: list[str] = Field(default_factory=list)
    selected_project_ids: list[str] = Field(default_factory=list)
    specialization_keywords: list[str] = Field(default_factory=list)
    generated_content: str | None = None
    is_active: bool = True


class ResumeProfileCreate(ResumeProfileBase):
    """Schema for creating a resume profile."""


class ResumeProfileUpdate(BaseModel):
    """Schema for updating a resume profile (partial)."""

    specialization: str | None = Field(None, pattern=SPECIALIZATION_PATTERN)
    profile_name: str | None = Field(None, min_length=1, max_length=100)
    headline: str | None = None
    summary: str | None = None
    selected_skills: list[str] | None = None
    selected_experience_ids: list[str] | None = None
    selected_project_ids: list[str] | None = None
    specialization_keywords: list[str] | None = None
    generated_content: str | None = None
    is_active: bool | None = None


class ResumeProfileResponse(ResumeProfileBase):
    """Schema for resume profile responses."""

    id: UUID
    candidate_profile_id: UUID

    model_config = {"from_attributes": True}


# === Resume recommendation (task spec #16) ===


class ResumeProfileScore(BaseModel):
    """Per-profile deterministic score with reasons."""

    resume_profile_id: UUID
    profile_name: str
    specialization: str
    score: float
    reasons: list[str] = Field(default_factory=list)


class ResumeRecommendationResponse(BaseModel):
    """Explained resume recommendation for a vacancy (task spec #16)."""

    recommended_profile_id: UUID | None = None
    recommended_profile_name: str | None = None
    recommended_specialization: str | None = None
    job_specializations: list[str] = Field(default_factory=list)
    scores: list[ResumeProfileScore] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


# === Resume Analysis (task spec #3-9) ===


class JobRequirementItem(BaseModel):
    """A single job requirement for evidence analysis."""

    skill: str = Field(..., description="Skill or technology name")
    importance: str = Field(default="PREFERRED", pattern="^(REQUIRED|PREFERRED|OPTIONAL)$")


class ResumeAnalysisRequest(BaseModel):
    """Request for resume analysis."""

    resume_text: str = Field(
        ...,
        min_length=50,
        max_length=100_000,
        description="Raw resume text to analyze",
    )
    job_requirements: list[JobRequirementItem] | None = Field(
        default=None,
        description="Optional job requirements for evidence mapping",
    )


class ATSIssueResponse(BaseModel):
    """An ATS check issue."""

    check: str
    severity: str
    detail: str
    location: str | None = None


class QualityDimensionResponse(BaseModel):
    """Quality dimension score."""

    dimension: str
    score: int
    issues: list[str] = Field(default_factory=list)
    positives: list[str] = Field(default_factory=list)


class BulletAnalysisResponse(BaseModel):
    """Single bullet analysis."""

    bullet: str
    experience_index: int = Field(ge=0)
    bullet_index: int = Field(ge=0)
    strength: str
    has_action: bool
    has_result: bool
    has_metric: bool
    issues: list[str] = Field(default_factory=list)


class EvidenceItemResponse(BaseModel):
    """Evidence for a requirement."""

    requirement: str
    importance: str
    strength: str
    source: str | None = None
    details: str | None = None


class ResumeAnalysisResponse(BaseModel):
    """Complete resume analysis result."""

    overall_ats_score: int = Field(..., ge=0, le=100, description="ATS readability score 0-100")
    overall_quality_score: int = Field(..., ge=0, le=100, description="Quality score 0-100")
    ats_issues: list[ATSIssueResponse] = Field(default_factory=list)
    ats_passed_checks: list[str] = Field(default_factory=list)
    quality_issues: list[QualityDimensionResponse] = Field(default_factory=list)
    bullet_analysis: list[BulletAnalysisResponse] = Field(default_factory=list)
    bullet_analysis_total: int = Field(default=0, ge=0)
    bullet_analysis_truncated: bool = False
    evidence: list[EvidenceItemResponse] = Field(default_factory=list)
    missing_required: list[str] = Field(default_factory=list, description="Required skills not in resume")
    weak_evidenced: list[str] = Field(default_factory=list, description="Skills only in skills section")
    recommendations: list[str] = Field(default_factory=list, description="Actionable recommendations")
