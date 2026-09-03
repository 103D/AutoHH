"""add package_data to applications

Revision ID: c9e2b3d4f5a6
Revises: b8f1a2c3d4e5
Create Date: 2026-08-29 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c9e2b3d4f5a6'
down_revision: Union[str, None] = 'b8f1a2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'applications',
        sa.Column('package_data', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('applications', 'package_data')
