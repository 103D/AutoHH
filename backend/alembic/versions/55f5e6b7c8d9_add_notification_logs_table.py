"""add notification_logs table

Revision ID: 55f5e6b7c8d9
Revises: 35e3f5ea0300
Create Date: 2026-08-20 22:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '55f5e6b7c8d9'
down_revision: Union[str, None] = '35e3f5ea0300'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('notification_logs',
    sa.Column('match_result_id', sa.Uuid(), nullable=False),
    sa.Column('telegram_message_id', sa.String(length=255), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('callback_action', sa.String(length=50), nullable=True),
    sa.Column('callback_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['match_result_id'], ['match_results.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_notification_logs_match_result', 'notification_logs', ['match_result_id'], unique=False)
    op.create_index('ix_notification_logs_status', 'notification_logs', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_notification_logs_status', table_name='notification_logs')
    op.drop_index('ix_notification_logs_match_result', table_name='notification_logs')
    op.drop_table('notification_logs')