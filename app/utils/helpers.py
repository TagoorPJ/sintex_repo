from datetime import datetime, timezone
from typing import List, Any


def get_current_time_str() -> str:
    """Return current UTC time as a readable string."""
    now = datetime.now(timezone.utc)
    return now.strftime("%A, %B %d, %Y %H:%M:%S UTC")


def truncate_messages(messages: List[Any], max_count: int = 25) -> List[Any]:
    """
    Keep only the last `max_count` messages to avoid context overflow.
    Always preserves ordering (oldest → newest).
    """
    if len(messages) <= max_count:
        return messages
    return messages[-max_count:]


def safe_strip(value: Any) -> str:
    """Safely strip whitespace from a value; returns empty string if None."""
    if value is None:
        return ""
    return str(value).strip()