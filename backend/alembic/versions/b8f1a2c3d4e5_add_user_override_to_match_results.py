"""add user_override_recommendation to match_results

Revision ID: b8f1a2c3d4e5
Revises: 66a7b8c9d0e1
Create Date: 2026-08-29 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b8f1a2c3d4e5'
down_revision: Union[str, None] = '66a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'match_results',
        sa.Column('user_override_recommendation', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('match_results', 'user_override_recommendation')
