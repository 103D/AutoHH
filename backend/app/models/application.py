"""Application model for tracking job applications."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Application(Base, UUIDMixin, TimestampMixin):
    """Track a job application."""

    __tablename__ = "applications"
    __table_args__ = (
        Index("ix_applications_job_candidate", "job_id", "candidate_profile_id", unique=True),
        Index("ix_applications_status", "status"),
    )

    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    candidate_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="DRAFT")
    # v2 flow: DISCOVERED -> SAVED -> PREPARED -> MANUALLY_APPLIED
    # legacy tracking: DRAFT, READY, APPLIED, SCREENING, INTERVIEW,
    # TECHNICAL_INTERVIEW, OFFER, REJECTED, WITHDRAWN, NO_RESPONSE, SKIPPED

    cover_letter: Mapped[str | None] = mapped_column(Text, nullable=True)
    adapted_resume: Mapped[str | None] = mapped_column(Text, nullable=True)

    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Generated application package (adapted resume + cover letter + diff)
    package_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # === Feedback loop (task spec #17): quality outcome events ===
    # Resume profile used for this application (Phase 3 selection)
    resume_profile_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("resume_profiles.id", ondelete="SET NULL"), nullable=True
    )
    # First response from the employer
    response_received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Outcome details
    interview_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    offer_salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    offer_salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ApplicationStatusHistory(Base, UUIDMixin, TimestampMixin):
    """Track status changes for an application (immutable history)."""

    __tablename__ = "application_status_history"
    __table_args__ = (
        Index("ix_status_history_application", "application_id"),
    )

    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )

    from_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    to_status: Mapped[str] = mapped_column(String(50), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
