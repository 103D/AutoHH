from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import JSON, ForeignKey

from app.models.base import Base, TimestampMixin, UUIDMixin

class JobSource(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "job_sources"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # api, scraper
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    
    last_fetch_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    fetch_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

class Job(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "jobs"

    source_id: Mapped[UUID] = mapped_column(ForeignKey("job_sources.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    
    employment_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    work_format: Mapped[str | None] = mapped_column(String(50), nullable=True)
    
    url: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Tracking
    first_seen_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # Deduplication
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    url_normalized: Mapped[str] = mapped_column(String(500), nullable=False)
    
    # Raw data
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)