"""add phase4 application outcomes

Revision ID: f8a9b0c1d2e3
Revises: e6f7a8b9c0d1
Create Date: 2026-09-03

Phase 4 (Feedback Loop):
- applications.resume_profile_id      — resume profile used (SET NULL on delete)
- applications.response_received_at   — first employer response timestamp
- applications.interview_stage        — stage reached (screening/technical/...)
- applications.rejection_reason       — why rejected
- applications.offer_salary_min/max   — offered salary range
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f8a9b0c1d2e3"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("resume_profile_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "applications",
        sa.Column("response_received_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "applications",
        sa.Column("interview_stage", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "applications",
        sa.Column("rejection_reason", sa.Text(), nullable=True),
    )
    op.add_column("applications", sa.Column("offer_salary_min", sa.Integer(), nullable=True))
    op.add_column("applications", sa.Column("offer_salary_max", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_applications_resume_profile_id",
        "applications",
        "resume_profiles",
        ["resume_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_applications_resume_profile_id", "applications", type_="foreignkey"
    )
    op.drop_column("applications", "offer_salary_max")
    op.drop_column("applications", "offer_salary_min")
    op.drop_column("applications", "rejection_reason")
    op.drop_column("applications", "interview_stage")
    op.drop_column("applications", "response_received_at")
    op.drop_column("applications", "resume_profile_id")
