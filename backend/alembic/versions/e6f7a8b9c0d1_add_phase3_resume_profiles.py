"""add phase3 resume profiles

Revision ID: e6f7a8b9c0d1
Revises: c3d4e5f6a7b8
Create Date: 2026-09-03

Phase 3 (Candidate / Resume system):
- candidate_profiles master-profile columns: experience, projects,
  certifications, skills_metadata (task spec #13)
- resume_profiles table: specialized resume presentations referencing the
  master profile without fact duplication (task spec #12)
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Master candidate profile: structured facts (task spec #13)
    op.add_column("candidate_profiles", sa.Column("experience", sa.JSON(), nullable=True))
    op.add_column("candidate_profiles", sa.Column("projects", sa.JSON(), nullable=True))
    op.add_column("candidate_profiles", sa.Column("certifications", sa.JSON(), nullable=True))
    op.add_column(
        "candidate_profiles",
        sa.Column("skills_metadata", sa.JSON(), nullable=False, server_default="{}"),
    )

    # Resume profiles: presentation layer referencing the master profile
    op.create_table(
        "resume_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_profile_id", sa.Uuid(), nullable=False),
        sa.Column("specialization", sa.String(length=50), nullable=False),
        sa.Column("profile_name", sa.String(length=100), nullable=False),
        sa.Column("headline", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("selected_skills", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("selected_experience_ids", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("selected_project_ids", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("specialization_keywords", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("generated_content", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_profile_id"],
            ["candidate_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_profile_id",
            "specialization",
            name="uq_resume_profiles_candidate_specialization",
        ),
    )
    op.create_index(
        op.f("ix_resume_profiles_candidate_profile_id"),
        "resume_profiles",
        ["candidate_profile_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_resume_profiles_candidate_profile_id"), table_name="resume_profiles"
    )
    op.drop_table("resume_profiles")
    op.drop_column("candidate_profiles", "skills_metadata")
    op.drop_column("candidate_profiles", "certifications")
    op.drop_column("candidate_profiles", "projects")
    op.drop_column("candidate_profiles", "experience")
