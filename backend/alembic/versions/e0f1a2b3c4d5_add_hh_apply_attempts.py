"""add hh_apply_attempts audit guard (ADR-001 milestone 5)

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-09-10

Durable audit-guard for explicit applies: unique (account, resume, vacancy)
so a retried call never issues a second remote POST. Account deletion
cascades; outcome + remote negotiation id + error stay for audit.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e0f1a2b3c4d5"
down_revision: str | None = "d9e0f1a2b3c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_TYPE = sa.dialects.postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "hh_apply_attempts",
        sa.Column("id", UUID_TYPE, primary_key=True),
        sa.Column(
            "hh_account_id",
            UUID_TYPE,
            sa.ForeignKey("hh_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("remote_resume_id", sa.String(length=64), nullable=False),
        sa.Column("remote_vacancy_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("remote_negotiation_id", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
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
            "remote_resume_id",
            "remote_vacancy_id",
            name="uq_hh_apply_account_resume_vacancy",
        ),
    )
    op.create_index("ix_hh_apply_account", "hh_apply_attempts", ["hh_account_id"])


def downgrade() -> None:
    op.drop_index("ix_hh_apply_account", table_name="hh_apply_attempts")
    op.drop_table("hh_apply_attempts")
