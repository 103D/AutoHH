"""Base AI provider interface and result schemas."""

from typing import Protocol

from pydantic import BaseModel, Field


class SkillMatch(BaseModel):
    """Matched or missing skill information."""

    skill: str
    match_type: str = "exact"  # exact, partial, related
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class JobRequirement(BaseModel):
    """A skill requirement extracted from a vacancy by the LLM.

    The LLM owns *semantic interpretation*: naming, normalization and the
    REQUIRED/PREFERRED/OPTIONAL classification. The numeric score is computed
    deterministically from these requirements by the scoring engine — the LLM
    never assigns the score itself (match model v3).
    """

    skill: str
    importance: str = "REQUIRED"  # REQUIRED | PREFERRED | OPTIONAL
    note: str | None = None


class SkillEquivalence(BaseModel):
    """A transferable/equivalent skill pair identified by the LLM.

    ``job_skill`` is a requirement that the candidate does not formally list;
    ``candidate_skill`` is the skill the candidate actually has that can be
    presented as related. The equivalence upgrades the requirement status to
    PARTIAL in the deterministic machinery.
    """

    job_skill: str
    candidate_skill: str
    note: str | None = None


class MatchResult(BaseModel):
    """Result of AI job analysis.

    ``score``/``recommendation`` are kept for backward compatibility with the
    provider contract but are NOT used in the final match verdict anymore —
    the engine recomputes everything deterministically from ``requirements``
    and ``skill_equivalences`` (match model v3).
    """

    score: int = Field(ge=0, le=100, description="Advisory compatibility score (ignored by the engine)")
    recommendation: str = Field(
        description="One of: HIGH_PRIORITY, APPLY, REVIEW, IGNORE (advisory)"
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
    # --- semantic interpretation (match model v3) ---
    requirements: list[JobRequirement] = Field(
        default_factory=list,
        description=(
            "Vacancy skill requirements classified REQUIRED/PREFERRED/OPTIONAL. "
            "Used by the engine to re-score deterministically."
        ),
    )
    skill_equivalences: list[SkillEquivalence] = Field(
        default_factory=list,
        description="Transferable/equivalent skills (downgrade MISSING -> PARTIAL).",
    )
    seniority_signal: str | None = Field(
        default=None, description="Inferred seniority of the role"
    )
    domain_signal: str | None = Field(
        default=None, description="Inferred domain (e.g. retail, product)"
    )
    tokens_used: int | None = Field(
        default=None, description="Number of tokens used in this request"
    )
    cost_usd: float | None = Field(
        default=None, description="Estimated cost in USD"
    )


class ParsedEducation(BaseModel):
    """Education entry extracted from a resume."""

    degree: str | None = None
    field: str | None = None
    institution: str | None = None
    graduation_year: int | None = Field(default=None, ge=1950, le=2100)


class ParsedSalaryExpectations(BaseModel):
    """Salary expectations extracted from a resume."""

    min: int | None = Field(default=None, ge=0)
    max: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, pattern="^[A-Z]{3}$")


class ParsedResume(BaseModel):
    """Structured data extracted from raw resume text."""

    full_name: str | None = None
    desired_positions: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    technologies: dict[str, list[str]] = Field(default_factory=dict)
    experience_years: int | None = Field(default=None, ge=0, le=50)
    experience_level: str | None = Field(
        default=None, pattern="^(junior|middle|senior|lead)$"
    )
    education: list[ParsedEducation] = Field(default_factory=list)
    languages: dict[str, str] = Field(default_factory=dict)
    location: str | None = None
    salary_expectations: ParsedSalaryExpectations | None = None
    employment_types: list[str] = Field(default_factory=list)
    work_formats: list[str] = Field(default_factory=list)
    relocation_possible: bool = False
    business_trips_acceptable: bool = False
    summary: str | None = None


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

    async def parse_resume(self, resume_text: str) -> ParsedResume:
        """
        Parse raw resume text into structured data.

        Args:
            resume_text: Full resume text

        Returns:
            ParsedResume with extracted structured data
        """
        ...
