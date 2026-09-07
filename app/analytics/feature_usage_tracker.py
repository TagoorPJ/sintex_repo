from __future__ import annotations

import os
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.analytics.feature_events import (
    COMPLETION_DETECTION_METHOD,
    FAILURE_DETECTION_METHOD,
    FEATURE_EVENTS,
)
from app.database import AsyncSessionLocal
from app.models import ChatbotFeatureUsageEvent
from app.utils.logger import get_logger

logger = get_logger(__name__)
_feature_context: ContextVar[dict | None] = ContextVar("feature_usage_context", default=None)


def _analytics_timezone():
    name = os.getenv("FEATURE_USAGE_TIMEZONE") or os.getenv("KPI_REPORT_TIMEZONE") or "Asia/Kolkata"
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        if name.strip().lower() in {"asia/kolkata", "asia/calcutta", "ist"}:
            return timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")
        if name.strip().lower() in {"utc", "etc/utc"}:
            return timezone.utc
        raise


def bind_feature_usage_context(
    *, user_id: int, conversation_id: int, message_id: int,
    mobile_number: str | None, user_message: str,
) -> None:
    """Bind the saved incoming message; binding alone never counts as usage."""
    _feature_context.set(dict(
        user_id=user_id, conversation_id=conversation_id, message_id=message_id,
        mobile_number=mobile_number, raw_user_message=user_message,
    ))


async def record_feature_result(
    event_key: str,
    *,
    success: bool,
    reason: str | None = None,
    context: dict | None = None,
) -> None:
    """Count a feature attempt and retain whether it succeeded or failed.

    QR callbacks supply their saved completion message as context because they
    run outside chat. Analytics failures must not fail the attempted action.
    """
    definition = FEATURE_EVENTS.get(event_key)
    event_context = context if context is not None else _feature_context.get()
    if definition is None or not event_context:
        return
    try:
        now = datetime.now(timezone.utc)
        values = {
            **event_context,
            "event_date": now.astimezone(_analytics_timezone()).date(),
            "event_key": event_key,
            "event_name": definition[0],
            "flow_name": definition[1],
            "option_number": None,
            "detection_method": (
                COMPLETION_DETECTION_METHOD if success else FAILURE_DETECTION_METHOD
            ),
            "confidence": None,
            "classifier_reason": (
                reason
                or ("Successful feature attempt" if success else "Failed feature attempt")
            )[:500],
            "created_at": now,
        }
        async with AsyncSessionLocal() as db:
            stmt = pg_insert(ChatbotFeatureUsageEvent).values(**values).on_conflict_do_nothing(
                index_elements=["message_id", "event_key"]
            )
            await db.execute(stmt)
            await db.commit()
    except Exception:
        logger.exception("[feature_usage] failed to record feature result | event=%s", event_key)


async def record_feature_completion(event_key: str, *, context: dict | None = None) -> None:
    """Backward-compatible success helper for non-API feature handlers."""
    await record_feature_result(event_key, success=True, context=context)
