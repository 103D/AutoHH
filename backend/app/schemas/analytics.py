"""Schemas for career analytics endpoints."""

from uuid import UUID

from pydantic import BaseModel, Field


class MarketOverviewResponse(BaseModel):
    """Aggregated market picture across analyzed vacancies."""

    candidate_profile_id: UUID
    total_analyzed: int
    by_category: dict[str, int] = Field(default_factory=dict)
    top_companies: list[dict] = Field(default_factory=list)
    demanded_skills: list[dict] = Field(default_factory=list)
    salary: dict = Field(default_factory=dict)


class SkillGapItem(BaseModel):
    """A single skill gap aggregated across vacancies."""

    skill: str
    in_jobs: int
    priority: str = Field(description="high | medium | low")


class SkillGapResponse(BaseModel):
    """Aggregated skill gaps for the candidate's target vacancies."""

    candidate_profile_id: UUID
    analyzed_vacancies: int
    gaps: list[SkillGapItem] = Field(default_factory=list)


class RoadmapStep(BaseModel):
    """One step of the learning roadmap."""

    position: int
    skill: str
    in_jobs: int
    priority: str
    rationale: str


class LearningRoadmapResponse(BaseModel):
    """Ordered learning roadmap derived from stretch vacancies."""

    candidate_profile_id: UUID
    steps: list[RoadmapStep] = Field(default_factory=list)
    total: int = 0


class DreamJobItem(BaseModel):
    """A dream-job entry for the analytics view."""

    job_id: UUID
    match_id: UUID
    title: str
    company: str
    url: str
    score: int
    category: str
    is_override: bool = False
    salary: dict = Field(default_factory=dict)


class DreamJobsResponse(BaseModel):
    """List of dream jobs (computed or user-overridden)."""

    candidate_profile_id: UUID
    total: int = 0
    jobs: list[DreamJobItem] = Field(default_factory=list)


class FeedbackBucketStat(BaseModel):
    """Outcome stats for one match-score bucket."""

    bucket: str
    applications: int = 0
    responses: int = 0
    interviews: int = 0
    offers: int = 0
    response_rate: float = 0.0
    interview_rate: float = 0.0
    offer_rate: float = 0.0


class FeedbackProfileStat(BaseModel):
    """Outcome stats for one resume profile."""

    resume_profile_id: str
    profile_name: str
    specialization: str
    applications: int = 0
    responses: int = 0
    interviews: int = 0
    offers: int = 0
    response_rate: float = 0.0
    interview_rate: float = 0.0
    offer_rate: float = 0.0


class FeedbackSpecializationStat(BaseModel):
    """Outcome stats for one job specialization."""

    specialization: str
    applications: int = 0
    responses: int = 0
    interviews: int = 0
    offers: int = 0
    response_rate: float = 0.0
    interview_rate: float = 0.0
    offer_rate: float = 0.0


class CountItem(BaseModel):
    """Generic named counter."""

    name: str
    count: int


class FeedbackResponse(BaseModel):
    """Aggregated feedback-loop report (task spec #17)."""

    total_applications: int = 0
    responded: int = 0
    interviews: int = 0
    response_rate: float = 0.0
    interview_rate: float = 0.0
    score_buckets: list[FeedbackBucketStat] = Field(default_factory=list)
    resume_profiles: list[FeedbackProfileStat] = Field(default_factory=list)
    specializations: list[FeedbackSpecializationStat] = Field(default_factory=list)
    rejection_reasons: list[CountItem] = Field(default_factory=list)
    missing_skills_on_rejection: list[CountItem] = Field(default_factory=list)
