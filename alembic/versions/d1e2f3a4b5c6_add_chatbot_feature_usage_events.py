"""add chatbot feature usage events

Revision ID: d1e2f3a4b5c6
Revises: c7e9a1b2d3f4
Create Date: 2026-09-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "c7e9a1b2d3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chatbot_feature_usage_events (
            id SERIAL PRIMARY KEY,
            event_date DATE NOT NULL,
            event_key VARCHAR(100) NOT NULL,
            event_name VARCHAR(200) NOT NULL,
            flow_name VARCHAR(100) NOT NULL,
            option_number VARCHAR(20),
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
            mobile_number VARCHAR(20),
            raw_user_message TEXT NOT NULL,
            detection_method VARCHAR(50) NOT NULL,
            confidence FLOAT,
            classifier_reason VARCHAR(500),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            CONSTRAINT uq_chatbot_feature_usage_message_event
                UNIQUE (message_id, event_key)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chatbot_feature_usage_events_event_date "
        "ON chatbot_feature_usage_events (event_date)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chatbot_feature_usage_events_event_key "
        "ON chatbot_feature_usage_events (event_key)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chatbot_feature_usage_events_flow_name "
        "ON chatbot_feature_usage_events (flow_name)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chatbot_feature_usage_events_user_id "
        "ON chatbot_feature_usage_events (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chatbot_feature_usage_events_conversation_id "
        "ON chatbot_feature_usage_events (conversation_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chatbot_feature_usage_events_message_id "
        "ON chatbot_feature_usage_events (message_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chatbot_feature_usage_events")
