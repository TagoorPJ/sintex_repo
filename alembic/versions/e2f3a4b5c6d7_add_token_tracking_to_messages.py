"""add token tracking to messages

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-09-24 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op


revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE messages
        ADD COLUMN IF NOT EXISTS prompt_tokens INTEGER NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS completion_tokens INTEGER NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS total_tokens INTEGER NOT NULL DEFAULT 0
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE messages
        DROP COLUMN IF EXISTS prompt_tokens,
        DROP COLUMN IF EXISTS completion_tokens,
        DROP COLUMN IF EXISTS total_tokens
        """
    )
