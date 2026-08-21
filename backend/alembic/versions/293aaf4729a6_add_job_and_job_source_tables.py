"""Add job and job_source tables

Revision ID: 293aaf4729a6
Revises: 8e796f013f86
Create Date: 2026-08-13 01:15:31.162829

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '293aaf4729a6'
down_revision: Union[str, None] = '8e796f013f86'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('job_sources',
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('type', sa.String(length=50), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('configuration', sa.JSON(), nullable=False),
    sa.Column('last_fetch_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('fetch_count', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('error_count', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_job_sources_name'), 'job_sources', ['name'], unique=True)

    op.create_table('jobs',
    sa.Column('source_id', sa.Uuid(), nullable=False),
    sa.Column('external_id', sa.String(length=255), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('company', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('location', sa.String(length=255), nullable=True),
    sa.Column('salary_min', sa.Integer(), nullable=True),
    sa.Column('salary_max', sa.Integer(), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('employment_type', sa.String(length=50), nullable=True),
    sa.Column('work_format', sa.String(length=50), nullable=True),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('url_normalized', sa.String(length=500), nullable=False),
    sa.Column('raw_data', sa.JSON(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['source_id'], ['job_sources.id']),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_jobs_company'), 'jobs', ['company'], unique=False)
    op.create_index(op.f('ix_jobs_external_id'), 'jobs', ['external_id'], unique=False)
    op.create_index(op.f('ix_jobs_location'), 'jobs', ['location'], unique=False)
    op.create_index(op.f('ix_jobs_source_id'), 'jobs', ['source_id'], unique=False)
    op.create_index('ix_jobs_source_external', 'jobs', ['source_id', 'external_id'], unique=False)
    op.create_index('ix_jobs_published_at', 'jobs', ['published_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_jobs_published_at', table_name='jobs')
    op.drop_index('ix_jobs_source_external', table_name='jobs')
    op.drop_index(op.f('ix_jobs_source_id'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_location'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_external_id'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_company'), table_name='jobs')
    op.drop_table('jobs')
    op.drop_index(op.f('ix_job_sources_name'), table_name='job_sources')
    op.drop_table('job_sources')