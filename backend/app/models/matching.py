from uuid import UUID

from sqlalchemy import ARRAY, JSON, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class MatchResult(Base, UUIDMixin, TimestampMixin):
    """Match analysis result between a job and candidate profile."""

    __tablename__ = "match_results"
    __table_args__ = (
        Index("ix_match_results_job_candidate", "job_id", "candidate_profile_id", unique=True),
        Index("ix_match_results_score", "score"),
        Index("ix_match_results_recommendation", "recommendation"),
    )

    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Overall score 0-100
    score: Mapped[int] = mapped_column(Integer, nullable=False)

    # Recommendation level
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)

    # AI Analysis - using ARRAY for PostgreSQL
    matched_skills: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    missing_skills: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    strong_matches: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    concerns: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    reasoning_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Score breakdown (deterministic components)
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)

    # AI metadata
    ai_provider: Mapped[str | None] = mapped_column(nullable=True)
    ai_model: Mapped[str | None] = mapped_column(nullable=True)
    ai_tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_cost_usd: Mapped[float | None] = mapped_column(nullable=True)

    analyzed_at: Mapped[str] = mapped_column(Text, nullable=False)  # ISO format timestamp
