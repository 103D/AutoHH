"""Phase 1 ingestion hardening.

- jobs.experience_required (normalized required experience years)
- job_sources.consecutive_errors (auto-disable health tracking)
- unique constraint on jobs.(source_id, external_id) — idempotency
- unique index on jobs.content_hash (matches the model)
- index on jobs.url_normalized (was missing from migrations)
- ON DELETE CASCADE job_sources -> jobs

Revision ID: 4a5b6c7d8e9
Revises: c9e2b3d4f5a6
Create Date: 2026-09-03 17:45:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "4a5b6c7d8e9"
down_revision: str | None = "c9e2b3d4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Normalized required experience (years) extracted deterministically by providers
    op.add_column("jobs", sa.Column("experience_required", sa.Integer(), nullable=True))

    # Auto-disable health tracking for job sources
    op.add_column(
        "job_sources",
        sa.Column("consecutive_errors", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )

    # Idempotency: one row per (source, external) vacancy.
    op.drop_index("ix_jobs_source_external", table_name="jobs")
    op.create_index("ix_jobs_source_external", "jobs", ["source_id", "external_id"], unique=True)

    # Match the ORM model: content_hash must be unique.
    op.create_index("uq_jobs_content_hash", "jobs", ["content_hash"], unique=True)

    # The model declares index=True ан url_normalized; it was missing from migrations.
    op.create_index("ix_jobs_url_normalized", "jobs", ["url_normalized"], unique=False)

    # Deleting a source cascades to its jobs now.
    op.drop_constraint("jobs_source_id_fkey", "jobs", type_="foreignkey")
    op.create_foreign_key(
        "jobs_source_id_fkey", "jobs", "job_sources", ["source_id"], ["id"], ondelete="CASCADE"
    )


def downgrade() -> None:
    op.drop_constraint("jobs_source_id_fkey", "jobs", type_="foreignkey")
    op.create_foreign_key("jobs_source_id_fkey", "jobs", "job_sources", ["source_id"], ["id"])

    op.drop_index("ix_jobs_url_normalized", table_name="jobs")
    op.drop_index("uq_jobs_content_hash", table_name="jobs")
    op.drop_index("ix_jobs_source_external", table_name="jobs")
    op.create_index("ix_jobs_source_external", "jobs", ["source_id", "external_id"], unique=False)

    op.drop_column("job_sources", "consecutive_errors")
    op.drop_column("jobs", "experience_required")
