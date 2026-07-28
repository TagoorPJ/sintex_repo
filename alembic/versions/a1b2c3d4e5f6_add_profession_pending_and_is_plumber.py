"""add profession_pending stage and is_plumber to users

Revision ID: a1b2c3d4e5f6
Revises: 372680394777
Create Date: 2026-05-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '587e1f437082'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_plumber column to users
    op.add_column('users', sa.Column('is_plumber', sa.Boolean(), nullable=True))

    # Add 'profession_pending' value to the conversation_stage_enum
    op.execute("ALTER TYPE conversation_stage_enum ADD VALUE IF NOT EXISTS 'profession_pending'")


def downgrade() -> None:
    op.drop_column('users', 'is_plumber')
    # Note: PostgreSQL does not support removing enum values; downgrade leaves the enum value intact
