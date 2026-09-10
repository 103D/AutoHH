"""add match current revision semantics

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-09-06

Append-only matching (ADR-002, milestone 3):
- match_results.is_current  — exactly one current revision per
  (job, candidate) pair;
- backfill legacy rows as current (safe: the old unique index guarantees at
  most one row per pair);
- replace the old unique (job, candidate) index with a partial unique index
  on (job, candidate) WHERE is_current, so new revisions can be inserted while
  the current one remains unique.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e3f4a5b6c7d8"
down_revision: str | None = "d2e3f4a5b6c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "match_results",
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.execute("UPDATE match_results SET is_current = TRUE")
    op.drop_index("ix_match_results_job_candidate", table_name="match_results")
    op.create_index(
        "ix_match_results_current_job_candidate",
        "match_results",
        ["job_id", "candidate_profile_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )


def downgrade() -> None:
    op.drop_index("ix_match_results_current_job_candidate", table_name="match_results")
    # Legacy index restoration is best-effort: it is only valid while no pair
    # has more than one revision.
    op.create_index(
        "ix_match_results_job_candidate",
        "match_results",
        ["job_id", "candidate_profile_id"],
        unique=True,
    )
    op.drop_column("match_results", "is_current")
