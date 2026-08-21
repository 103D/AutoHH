"""add match_results table

Revision ID: 35e3f5ea0300
Revises: 40a1b2c3d4e5
Create Date: 2026-08-17 20:47:30.838038

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '35e3f5ea0300'
down_revision: Union[str, None] = '40a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('match_results',
    sa.Column('job_id', sa.Uuid(), nullable=False),
    sa.Column('candidate_profile_id', sa.Uuid(), nullable=False),
    sa.Column('score', sa.Integer(), nullable=False),
    sa.Column('recommendation', sa.Text(), nullable=False),
    sa.Column('matched_skills', sa.ARRAY(sa.Text()), nullable=False),
    sa.Column('missing_skills', sa.ARRAY(sa.Text()), nullable=False),
    sa.Column('strong_matches', sa.ARRAY(sa.Text()), nullable=False),
    sa.Column('concerns', sa.ARRAY(sa.Text()), nullable=False),
    sa.Column('reasoning_summary', sa.Text(), nullable=True),
    sa.Column('score_breakdown', sa.JSON(), nullable=False),
    sa.Column('ai_provider', sa.String(), nullable=True),
    sa.Column('ai_model', sa.String(), nullable=True),
    sa.Column('ai_tokens_used', sa.Integer(), nullable=True),
    sa.Column('ai_cost_usd', sa.Float(), nullable=True),
    sa.Column('analyzed_at', sa.Text(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['candidate_profile_id'], ['candidate_profiles.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_match_results_candidate_profile_id'), 'match_results', ['candidate_profile_id'], unique=False)
    op.create_index('ix_match_results_job_candidate', 'match_results', ['job_id', 'candidate_profile_id'], unique=True)
    op.create_index(op.f('ix_match_results_job_id'), 'match_results', ['job_id'], unique=False)
    op.create_index('ix_match_results_recommendation', 'match_results', ['recommendation'], unique=False)
    op.create_index('ix_match_results_score', 'match_results', ['score'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_match_results_score', table_name='match_results')
    op.drop_index('ix_match_results_recommendation', table_name='match_results')
    op.drop_index(op.f('ix_match_results_job_id'), table_name='match_results')
    op.drop_index('ix_match_results_job_candidate', table_name='match_results')
    op.drop_index(op.f('ix_match_results_candidate_profile_id'), table_name='match_results')
    op.drop_table('match_results')