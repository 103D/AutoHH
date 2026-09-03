from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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
    business_trips_acceptable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Resume versions
    resume_versions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Master candidate profile (task spec #13): single source of truth for
    # the candidate's facts. Referenced by ResumeProfiles — never duplicated.
    # experience: [{id, company, title, period_start, period_end, description,
    #               achievements, skills}]
    experience: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    # projects: [{id, name, role, description, technologies, results}]
    projects: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    # certifications: [{name, issuer, year, url}]
    certifications: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    # Per-skill metadata keyed by canonical skill name (task spec #13):
    # {skill: {category, confidence, experience_level, production_experience, years}}
    skills_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Additional
    additional_preferences: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ResumeProfile(Base, UUIDMixin, TimestampMixin):
    """Specialized resume presentation built on top of the master profile.

    Holds only presentation-level data (headline, summary, keywords) and
    references into the master CandidateProfile (selected_skills,
    selected_experience_ids, selected_project_ids) — the actual experience is
    never duplicated across profiles (task spec #12):

        Master Candidate Profile
                  |
        Resume Profiles (DATA_ANALYST / BI_ANALYST / PRODUCT_ANALYST /
                         RETAIL_COMMERCIAL_ANALYST)
    """

    __tablename__ = "resume_profiles"

    candidate_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    specialization: Mapped[str] = mapped_column(String(50), nullable=False)
    profile_name: Mapped[str] = mapped_column(String(100), nullable=False)
    headline: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # References into the master profile — facts live only there.
    selected_skills: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    selected_experience_ids: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, nullable=False
    )
    selected_project_ids: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, nullable=False
    )
    specialization_keywords: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, nullable=False
    )
    # Optional rendered resume text for this specialization.
    generated_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "candidate_profile_id",
            "specialization",
            name="uq_resume_profiles_candidate_specialization",
        ),
    )
