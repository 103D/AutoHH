"""add phase5 optimization

Revision ID: a1b2c3d4e5f6
Revises: f8a9b0c1d2e3
Create Date: 2026-09-03

Phase 5 (Optimization):
- jobs.source_type — persisted denormalized source type; removes the transient
  ``job.source`` Python-side hack (audit debt item) and enables source filters
  without a JOIN.
- Backfill from job_sources.type for all existing rows.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f8a9b0c1d2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("source_type", sa.String(length=50), nullable=True))
    op.create_index("ix_jobs_source_type", "jobs", ["source_type"], unique=False)
    # Backfill existing rows from the parent job_sources row.
    op.execute(
        "UPDATE jobs SET source_type = job_sources.type "
        "FROM job_sources WHERE jobs.source_id = job_sources.id"
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_source_type", table_name="jobs")
    op.drop_column("jobs", "source_type")
