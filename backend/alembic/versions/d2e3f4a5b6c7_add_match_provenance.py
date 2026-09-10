"""add match provenance fingerprints

Revision ID: d2e3f4a5b6c7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-06

Additive milestone for reproducible matching. Legacy rows intentionally keep
nullable fingerprints and are treated as stale by MatchingService. Append-only
revisions and replacement of the current unique constraint are a later rollout.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in (
        "candidate_fingerprint",
        "job_fingerprint",
        "scoring_fingerprint",
        "taxonomy_fingerprint",
        "analysis_fingerprint",
    ):
        op.add_column(
            "match_results",
            sa.Column(column, sa.String(length=64), nullable=True),
        )

    for column in ("taxonomy_version", "engine_version", "prompt_version"):
        op.add_column(
            "match_results",
            sa.Column(column, sa.String(length=50), nullable=True),
        )

    op.add_column(
        "match_results",
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_index(
        "ix_match_results_analysis_fingerprint",
        "match_results",
        ["analysis_fingerprint"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_match_results_analysis_fingerprint", table_name="match_results")
    op.drop_column("match_results", "revision")
    for column in ("prompt_version", "engine_version", "taxonomy_version"):
        op.drop_column("match_results", column)
    for column in (
        "analysis_fingerprint",
        "taxonomy_fingerprint",
        "scoring_fingerprint",
        "job_fingerprint",
        "candidate_fingerprint",
    ):
        op.drop_column("match_results", column)
