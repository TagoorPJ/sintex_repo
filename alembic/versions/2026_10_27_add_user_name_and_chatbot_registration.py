"""add user name and chatbot registration fields

Revision ID: 2026_10_27_user_name_chatbot
Revises: e2f3a4b5c6d7
Create Date: 2026-10-27 13:16:00

"""
from typing import Sequence, Union

from alembic import op
# pyrefly: ignore[missing-import]
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2026_10_27_user_name_chatbot'
down_revision: Union[str, None] = 'e2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # Safe check / add columns
    op.execute(sa.text("ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(150);"))
    op.execute(sa.text("ALTER TABLE users ADD COLUMN IF NOT EXISTS registered_via_chatbot BOOLEAN NOT NULL DEFAULT FALSE;"))
    op.execute(sa.text("ALTER TABLE users ADD COLUMN IF NOT EXISTS registered_at TIMESTAMP WITH TIME ZONE;"))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS registered_at;"))
    op.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS registered_via_chatbot;"))
    op.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS name;"))
