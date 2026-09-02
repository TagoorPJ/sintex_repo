"""add last_response to external api daily counts

Revision ID: b4d2e6f8a901
Revises: 9c7f0e1a2b3c
Create Date: 2026-09-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4d2e6f8a901"
down_revision: Union[str, None] = "9c7f0e1a2b3c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE external_api_daily_counts "
        "ADD COLUMN IF NOT EXISTS last_response TEXT"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE external_api_daily_counts "
        "DROP COLUMN IF EXISTS last_response"
    )
