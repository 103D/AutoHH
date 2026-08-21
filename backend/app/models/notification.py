"""Notification log model for tracking sent Telegram notifications."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class NotificationLog(Base, UUIDMixin, TimestampMixin):
    """Track notifications sent to user about job matches."""

    __tablename__ = "notification_logs"
    __table_args__ = (
        Index("ix_notification_logs_match_result", "match_result_id"),
        Index("ix_notification_logs_status", "status"),
    )

    match_result_id: Mapped[UUID] = mapped_column(
        ForeignKey("match_results.id", ondelete="CASCADE"), nullable=False
    )

    telegram_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending"
    )  # pending, sent, failed, callback
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    callback_action: Mapped[str | None] = mapped_column(String(50), nullable=True)
    callback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
