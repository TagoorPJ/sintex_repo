"""add external api daily counts

Revision ID: 9c7f0e1a2b3c
Revises: a1b2c3d4e5f6
Create Date: 2026-09-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9c7f0e1a2b3c"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Some deployments started the app before this migration was applied,
    # so Base.metadata.create_all may already have created this table.
    # In that case, keep the existing table and add the field this revision
    # needs instead of failing with "relation already exists".
    if inspector.has_table("external_api_daily_counts"):
        columns = {
            column["name"]
            for column in inspector.get_columns("external_api_daily_counts")
        }
        if "last_response" not in columns:
            op.add_column(
                "external_api_daily_counts",
                sa.Column("last_response", sa.Text(), nullable=True),
            )
        return

    op.create_table(
        "external_api_daily_counts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("call_date", sa.Date(), nullable=False),
        sa.Column("api_name", sa.String(length=100), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("endpoint", sa.String(length=255), nullable=False),
        sa.Column("total_calls", sa.BigInteger(), nullable=False),
        sa.Column("success_calls", sa.BigInteger(), nullable=False),
        sa.Column("failure_calls", sa.BigInteger(), nullable=False),
        sa.Column("total_duration_ms", sa.Float(), nullable=False),
        sa.Column("max_duration_ms", sa.Float(), nullable=False),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column("last_response", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_called_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "call_date",
            "api_name",
            "method",
            "endpoint",
            name="uq_external_api_daily_counts_day_api",
        ),
    )
    op.create_index(
        op.f("ix_external_api_daily_counts_api_name"),
        "external_api_daily_counts",
        ["api_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_external_api_daily_counts_call_date"),
        "external_api_daily_counts",
        ["call_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_external_api_daily_counts_id"),
        "external_api_daily_counts",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_external_api_daily_counts_id"),
        table_name="external_api_daily_counts",
    )
    op.drop_index(
        op.f("ix_external_api_daily_counts_call_date"),
        table_name="external_api_daily_counts",
    )
    op.drop_index(
        op.f("ix_external_api_daily_counts_api_name"),
        table_name="external_api_daily_counts",
    )
    op.drop_table("external_api_daily_counts")
