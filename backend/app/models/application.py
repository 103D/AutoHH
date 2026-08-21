"""Application model for tracking job applications."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
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
    # DRAFT, READY, APPLIED, SCREENING, INTERVIEW, TECHNICAL_INTERVIEW,
    # OFFER, REJECTED, WITHDRAWN, NO_RESPONSE

    cover_letter: Mapped[str | None] = mapped_column(Text, nullable=True)
    adapted_resume: Mapped[str | None] = mapped_column(Text, nullable=True)

    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


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
