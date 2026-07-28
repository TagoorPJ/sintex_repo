"""add user_id to messages table

Revision ID: dbad22a9207d
Revises: 276bfcdcb004
Create Date: 2026-05-01 15:48:26.717897
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "dbad22a9207d"
down_revision: Union[str, None] = "276bfcdcb004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ✅ add as nullable first
    op.add_column("messages", sa.Column("user_id", sa.Integer(), nullable=True))

    # ✅ backfill existing rows from conversations.user_id
    op.execute("""
        UPDATE messages m
        SET user_id = c.user_id
        FROM conversations c
        WHERE m.conversation_id = c.id
    """)

    # ✅ make not null after data fill
    op.alter_column("messages", "user_id", nullable=False)

    # ✅ index + FK
    op.create_index("ix_messages_user_id", "messages", ["user_id"], unique=False)

    op.create_foreign_key(
        "fk_messages_user_id_users",
        "messages",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE"
    )


def downgrade() -> None:
    op.drop_constraint("fk_messages_user_id_users", "messages", type_="foreignkey")
    op.drop_index("ix_messages_user_id", table_name="messages")
    op.drop_column("messages", "user_id")