"""add api health rollup fields

Revision ID: c7e9a1b2d3f4
Revises: b4d2e6f8a901
Create Date: 2026-09-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "c7e9a1b2d3f4"
down_revision: Union[str, None] = "b4d2e6f8a901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE external_api_daily_counts "
        "ADD COLUMN IF NOT EXISTS status_codes TEXT"
    )
    op.execute(
        "ALTER TABLE external_api_daily_counts "
        "ADD COLUMN IF NOT EXISTS error_messages TEXT"
    )
    op.execute(
        "UPDATE external_api_daily_counts "
        "SET status_codes = last_status_code::text "
        "WHERE status_codes IS NULL AND last_status_code IS NOT NULL"
    )
    op.execute(
        "UPDATE external_api_daily_counts "
        "SET error_messages = last_error "
        "WHERE error_messages IS NULL AND last_error IS NOT NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE external_api_daily_counts "
        "DROP COLUMN IF EXISTS error_messages"
    )
    op.execute(
        "ALTER TABLE external_api_daily_counts "
        "DROP COLUMN IF EXISTS status_codes"
    )
