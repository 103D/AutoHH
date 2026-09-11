"""add hh_resumes and hh_negotiations (ADR-001 milestone 3)

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-09-06

Read-only remote snapshots for the HH applicant account: resumes and
negotiations. Unique per (hh_account, remote id); optional links to local
resume_profiles / jobs / applications arrive as nullable columns now and get
populated in milestone 4. Account deletion cascades; local-link deletion
leaves remote rows (SET NULL).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d9e0f1a2b3c4"
down_revision: str | None = "c8d9e0f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_TYPE = sa.dialects.postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "hh_resumes",
        sa.Column("id", UUID_TYPE, primary_key=True),
        sa.Column(
            "hh_account_id",
            UUID_TYPE,
            sa.ForeignKey("hh_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("remote_resume_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("remote_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "resume_profile_id",
            UUID_TYPE,
            sa.ForeignKey("resume_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "hh_account_id", "remote_resume_id", name="uq_hh_resumes_account_remote"
        ),
    )
    op.create_index("ix_hh_resumes_account", "hh_resumes", ["hh_account_id"])

    op.create_table(
        "hh_negotiations",
        sa.Column("id", UUID_TYPE, primary_key=True),
        sa.Column(
            "hh_account_id",
            UUID_TYPE,
            sa.ForeignKey("hh_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("remote_negotiation_id", sa.String(length=64), nullable=False),
        sa.Column("remote_resume_id", sa.String(length=64), nullable=True),
        sa.Column("remote_vacancy_id", sa.String(length=64), nullable=True),
        sa.Column("state_id", sa.String(length=64), nullable=True),
        sa.Column("state_name", sa.String(length=255), nullable=True),
        sa.Column("remote_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remote_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("messages_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("raw_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "job_id",
            UUID_TYPE,
            sa.ForeignKey("jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "application_id",
            UUID_TYPE,
            sa.ForeignKey("applications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "hh_account_id",
            "remote_negotiation_id",
            name="uq_hh_negotiations_account_remote",
        ),
    )
    op.create_index("ix_hh_negotiations_account", "hh_negotiations", ["hh_account_id"])
    op.create_index("ix_hh_negotiations_vacancy", "hh_negotiations", ["remote_vacancy_id"])


def downgrade() -> None:
    op.drop_index("ix_hh_negotiations_vacancy", table_name="hh_negotiations")
    op.drop_index("ix_hh_negotiations_account", table_name="hh_negotiations")
    op.drop_table("hh_negotiations")
    op.drop_index("ix_hh_resumes_account", table_name="hh_resumes")
    op.drop_table("hh_resumes")
