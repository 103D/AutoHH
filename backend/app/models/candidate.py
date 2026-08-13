from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin

class CandidateProfile(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "candidate_profiles"

    user_id: Mapped[UUID] = mapped_column(nullable=False, unique=True)

    # Basics
    desired_positions: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    skills: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    technologies: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    # Experience
    experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    experience_level: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Education
    education: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)

    # Languages
    languages: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)

    # Preferences
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    desired_salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    desired_salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_currency: Mapped[str] = mapped_column(String(3), default="KZT", nullable=False)
    employment_types: Mapped[list[str] | None] = mapped_column(ARRAY(String(50)), nullable=True)
    work_formats: Mapped[list[str] | None] = mapped_column(ARRAY(String(50)), nullable=True)
    relocation_possible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    business_trips_acceptable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Resume versions
    resume_versions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Additional
    additional_preferences: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)