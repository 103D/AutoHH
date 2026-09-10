"""add hh_accounts table (ADR-001 milestone 1-2)

Revision ID: c8d9e0f1a2b3
Revises: e3f4a5b6c7d8
Create Date: 2026-09-06

Creates the HH account bounded context table: one connected applicant
account per (user_id, host) and per (hh_user_id, host). Tokens are stored
Fernet-encrypted; the encryption key lives in HH_CREDENTIALS_KEY.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: str | None = "e3f4a5b6c7d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hh_accounts",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("hh_user_id", sa.String(length=64), nullable=False),
        sa.Column("host", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="CONNECTED"),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=False),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "host", name="uq_hh_accounts_user_host"),
        sa.UniqueConstraint("hh_user_id", "host", name="uq_hh_accounts_hh_user_host"),
    )
    op.create_index("ix_hh_accounts_status", "hh_accounts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_hh_accounts_status", table_name="hh_accounts")
    op.drop_table("hh_accounts")
