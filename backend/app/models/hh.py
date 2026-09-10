"""HH account models (ADR-001 bounded context).

``hh_accounts`` stores one connected HeadHunter applicant account per local
user and host. Tokens are stored Fernet-encrypted (``HH_CREDENTIALS_KEY``);
plaintext tokens must never reach this table, logs or the API layer.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class HHAccountStatus:
    """Lifecycle of a connected HH account (ADR-001)."""

    CONNECTED = "CONNECTED"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"

    ALL: list[str] = [CONNECTED, REAUTH_REQUIRED]


class HHAccount(Base, UUIDMixin, TimestampMixin):
    """Connected HeadHunter applicant account with encrypted credentials."""

    __tablename__ = "hh_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "host", name="uq_hh_accounts_user_host"),
        UniqueConstraint("hh_user_id", "host", name="uq_hh_accounts_hh_user_host"),
        Index("ix_hh_accounts_status", "status"),
    )

    # Local owner of the connection. No FK yet: a real users table arrives
    # with the authentication boundary (ADR-001 production gate).
    user_id: Mapped[UUID] = mapped_column(nullable=False)

    hh_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    host: Mapped[str] = mapped_column(String(64), default="hh.ru", nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=HHAccountStatus.CONNECTED, nullable=False
    )

    # Fernet ciphertexts (CredentialCipher) — never plaintext.
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    access_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scopes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class HHResume(Base, UUIDMixin, TimestampMixin):
    """Remote HH applicant resume snapshot (read-only sync, ADR-001 m3).

    ``raw_data`` keeps the remote payload verbatim; ``content_hash`` makes
    repeated syncs idempotent (unchanged items are not rewritten).
    """

    __tablename__ = "hh_resumes"
    __table_args__ = (
        UniqueConstraint(
            "hh_account_id", "remote_resume_id", name="uq_hh_resumes_account_remote"
        ),
        Index("ix_hh_resumes_account", "hh_account_id"),
    )

    hh_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("hh_accounts.id", ondelete="CASCADE"), nullable=False
    )
    remote_resume_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # Remote snapshot (data, not workflow rules — ADR-001)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    remote_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Optional link to the local presentation profile (ADR-001 milestone 4)
    resume_profile_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("resume_profiles.id", ondelete="SET NULL"), nullable=True
    )


class HHNegotiation(Base, UUIDMixin, TimestampMixin):
    """Remote HH negotiation (applicant response) snapshot, ADR-001 m3.

    The applicant-visible state is treated as remote data, never mapped onto
    the local Application workflow (which stays the product source of truth).
    """

    __tablename__ = "hh_negotiations"
    __table_args__ = (
        UniqueConstraint(
            "hh_account_id",
            "remote_negotiation_id",
            name="uq_hh_negotiations_account_remote",
        ),
        Index("ix_hh_negotiations_account", "hh_account_id"),
        Index("ix_hh_negotiations_vacancy", "remote_vacancy_id"),
    )

    hh_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("hh_accounts.id", ondelete="CASCADE"), nullable=False
    )
    remote_negotiation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    remote_resume_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    remote_vacancy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Applicant-visible remote state (data, not workflow rules — ADR-001)
    state_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remote_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    remote_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    messages_metadata: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False
    )
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Optional links to the local workflow (ADR-001 milestone 4)
    job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    application_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL"), nullable=True
    )


class HHApplyAttemptStatus:
    """Durable outcome of one explicit HH apply (ADR-001 milestone 5)."""

    IN_PROGRESS = "IN_PROGRESS"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"

    ALL: list[str] = [IN_PROGRESS, SUCCEEDED, FAILED]


class HHApplyAttempt(Base, UUIDMixin, TimestampMixin):
    """Audit-guard row for one explicit apply keyed by the durable triple.

    The unique constraint on (account, resume, vacancy) is the idempotency
    guard: at most one logical apply exists per triple, and a repeated call
    never issues a second remote POST. FAILED rows stay retryable; orphaned
    IN_PROGRESS rows become retryable after ``STALE_IN_PROGRESS_SECONDS``.
    """

    __tablename__ = "hh_apply_attempts"
    __table_args__ = (
        UniqueConstraint(
            "hh_account_id",
            "remote_resume_id",
            "remote_vacancy_id",
            name="uq_hh_apply_account_resume_vacancy",
        ),
        Index("ix_hh_apply_account", "hh_account_id"),
    )

    hh_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("hh_accounts.id", ondelete="CASCADE"), nullable=False
    )
    remote_resume_id: Mapped[str] = mapped_column(String(64), nullable=False)
    remote_vacancy_id: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[str] = mapped_column(
        String(32), default=HHApplyAttemptStatus.IN_PROGRESS, nullable=False
    )
    remote_negotiation_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
