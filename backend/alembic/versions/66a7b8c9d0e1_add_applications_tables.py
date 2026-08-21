"""add applications tables

Revision ID: 66a7b8c9d0e1
Revises: 55f5e6b7c8d9
Create Date: 2026-08-21 07:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '66a7b8c9d0e1'
down_revision: Union[str, None] = '55f5e6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('applications',
    sa.Column('job_id', sa.Uuid(), nullable=False),
    sa.Column('candidate_profile_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('cover_letter', sa.Text(), nullable=True),
    sa.Column('adapted_resume', sa.Text(), nullable=True),
    sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['candidate_profile_id'], ['candidate_profiles.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_applications_job_candidate', 'applications', ['job_id', 'candidate_profile_id'], unique=True)
    op.create_index('ix_applications_status', 'applications', ['status'], unique=False)

    op.create_table('application_status_history',
    sa.Column('application_id', sa.Uuid(), nullable=False),
    sa.Column('from_status', sa.String(length=50), nullable=True),
    sa.Column('to_status', sa.String(length=50), nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_status_history_application', 'application_status_history', ['application_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_status_history_application', table_name='application_status_history')
    op.drop_table('application_status_history')
    op.drop_index('ix_applications_status', table_name='applications')
    op.drop_index('ix_applications_job_candidate', table_name='applications')
    op.drop_table('applications')