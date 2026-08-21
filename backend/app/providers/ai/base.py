"""Base AI provider interface and result schemas."""

from typing import Protocol

from pydantic import BaseModel, Field


class SkillMatch(BaseModel):
    """Matched or missing skill information."""

    skill: str
    match_type: str = "exact"  # exact, partial, related
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class MatchResult(BaseModel):
    """Result of AI job analysis."""

    score: int = Field(ge=0, le=100, description="Overall compatibility score")
    recommendation: str = Field(
        description="One of: HIGH_PRIORITY, APPLY, REVIEW, IGNORE"
    )
    matched_skills: list[SkillMatch] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    strong_matches: list[str] = Field(
        default_factory=list, description="Key strengths for this role"
    )
    concerns: list[str] = Field(
        default_factory=list, description="Potential concerns or gaps"
    )
    reasoning_summary: str = Field(description="Brief explanation of the match")
    salary_match: bool | None = Field(
        default=None, description="Whether salary expectations align"
    )
    location_match: bool | None = Field(
        default=None, description="Whether location aligns"
    )
    experience_match: bool | None = Field(
        default=None, description="Whether experience level aligns"
    )
    tokens_used: int | None = Field(
        default=None, description="Number of tokens used in this request"
    )
    cost_usd: float | None = Field(
        default=None, description="Estimated cost in USD"
    )


class AIProvider(Protocol):
    """Abstract interface for AI providers."""

    async def analyze_job(
        self,
        job_title: str,
        job_company: str,
        job_description: str,
        job_requirements: dict | None,
        candidate_profile: dict,
    ) -> MatchResult:
        """
        Analyze job against candidate profile.

        Args:
            job_title: Job title
            job_company: Company name
            job_description: Job description text
            job_requirements: Structured job requirements (location, salary, etc.)
            candidate_profile: Candidate profile as dict

        Returns:
            MatchResult with analysis
        """
        ...

    async def adapt_resume(
        self,
        resume_text: str,
        job_title: str,
        job_description: str,
        key_requirements: list[str],
    ) -> str:
        """
        Adapt resume for specific job.

        Args:
            resume_text: Original resume text
            job_title: Target job title
            job_description: Job description
            key_requirements: Key requirements to highlight

        Returns:
            Adapted resume text
        """
        ...

    async def generate_cover_letter(
        self,
        candidate_name: str,
        job_title: str,
        company_name: str,
        job_description: str,
        key_matches: list[str],
        style: str = "professional",
    ) -> str:
        """
        Generate cover letter for job application.

        Args:
            candidate_name: Candidate's name
            job_title: Job title
            company_name: Company name
            job_description: Job description
            key_matches: Key matching points to highlight
            style: Cover letter style (professional, casual, enthusiastic)

        Returns:
            Generated cover letter text
        """
        ...
