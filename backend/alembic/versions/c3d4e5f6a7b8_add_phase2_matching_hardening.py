"""add phase2 matching hardening

Revision ID: c3d4e5f6a7b8
Revises: 4a5b6c7d8e9
Create Date: 2026-09-03

Phase 2 (Matching Engine):
- match_results.hard_failures  — hard requirement failures (NOT_ELIGIBLE)
- jobs.specializations         — multi-label specialization classification
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "match_results",
        sa.Column(
            "hard_failures",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "jobs",
        sa.Column("specializations", postgresql.ARRAY(sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("jobs", "specializations")
    op.drop_column("match_results", "hard_failures")
