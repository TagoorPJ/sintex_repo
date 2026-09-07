from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import AsyncSessionLocal
from app.analytics.feature_events import API_FEATURE_EVENTS
from app.analytics.feature_usage_tracker import record_feature_result
from app.models import ExternalApiDailyCount
from app.utils.logger import get_logger

logger = get_logger(__name__)

TRACKED_API_PREFIX = "evolve."
MAX_STORED_RESPONSE_CHARS = 4000

_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_conversation_id: ContextVar[str | None] = ContextVar("conversation_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)
_mobile_number: ContextVar[str | None] = ContextVar("mobile_number", default=None)


def new_trace_id(prefix: str = "req") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@contextmanager
def trace_context(
    *,
    trace_id: str | None = None,
    conversation_id: str | int | None = None,
    user_id: str | int | None = None,
    mobile_number: str | None = None,
):
    tokens = [
        (_trace_id, _trace_id.set(str(trace_id) if trace_id else new_trace_id())),
        (
            _conversation_id,
            _conversation_id.set(str(conversation_id) if conversation_id is not None else None),
        ),
        (_user_id, _user_id.set(str(user_id) if user_id is not None else None)),
        (_mobile_number, _mobile_number.set(str(mobile_number) if mobile_number else None)),
    ]
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


def current_trace_fields() -> dict[str, str]:
    fields = {
        "trace_id": _trace_id.get(),
        "conversation_id": _conversation_id.get(),
        "user_id": _user_id.get(),
        "mobile_number": _mobile_number.get(),
    }
    return {key: value for key, value in fields.items() if value}


def bind_trace_context(
    *,
    trace_id: str | None = None,
    conversation_id: str | int | None = None,
    user_id: str | int | None = None,
    mobile_number: str | None = None,
) -> str:
    resolved_trace_id = trace_id or _trace_id.get() or new_trace_id()
    _trace_id.set(str(resolved_trace_id))
    if conversation_id is not None:
        _conversation_id.set(str(conversation_id))
    if user_id is not None:
        _user_id.set(str(user_id))
    if mobile_number:
        _mobile_number.set(str(mobile_number))
    return str(resolved_trace_id)


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


def _clean_value(value: Any) -> str:
    text = str(value)
    if len(text) > 300:
        return text[:297] + "..."
    return text


def _is_tracked_api(api_name: str | None) -> bool:
    return str(api_name or "").startswith(TRACKED_API_PREFIX)


def _response_preview(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if hasattr(value, "text"):
            text = value.text
        else:
            text = str(value)
    except Exception:
        return None
    text = text.strip()
    if not text:
        return None
    if len(text) > MAX_STORED_RESPONSE_CHARS:
        return text[:MAX_STORED_RESPONSE_CHARS] + "...[truncated]"
    return text


def _status_codes_text(status_code: int | None) -> str | None:
    if status_code is None:
        return None
    return str(status_code)


def _append_distinct_csv(existing: str | None, value: str | None, *, limit: int = 20) -> str | None:
    values = []
    seen = set()
    for item in str(existing or "").split(","):
        item = item.strip()
        if item and item not in seen:
            seen.add(item)
            values.append(item)
    if value and value not in seen:
        values.append(value)
    if not values:
        return None
    return ",".join(values[-limit:])


def _append_distinct_messages(
    existing: str | None,
    value: str | None,
    *,
    limit: int = 20,
) -> str | None:
    messages = []
    seen = set()
    for item in str(existing or "").split("\n---\n"):
        item = " ".join(item.split())
        if item and item not in seen:
            seen.add(item)
            messages.append(item)
    value = " ".join(str(value or "").split())
    if value and value not in seen:
        messages.append(value)
    if not messages:
        return None
    return "\n---\n".join(messages[-limit:])[:4000]


def _response_json(value: Any) -> Any:
    try:
        return value.json()
    except Exception:
        return None


def _success_from_response(
    response: Any,
    success_statuses: Iterable[int] | None,
) -> bool:
    status_code = getattr(response, "status_code", None)
    if not _status_success(status_code, success_statuses):
        return False

    data = _response_json(response)
    if isinstance(data, dict):
        for key in ("status", "success", "ok", "result"):
            if key not in data:
                continue
            value = data.get(key)
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in {
                "success",
                "succeeded",
                "ok",
                "true",
                "1",
            }

    return True


def _error_from_response(response: Any, success: bool) -> str | None:
    if success:
        return None

    data = _response_json(response)
    status_code = getattr(response, "status_code", None)
    if isinstance(data, dict):
        parts = []
        for key in ("status", "success", "ok", "result", "message", "error", "detail"):
            value = data.get(key)
            if value is not None:
                parts.append(f"{key}={value}")
        if parts:
            return " | ".join(parts)[:1000]

    preview = _response_preview(response)
    if preview:
        return f"status_code={status_code} | response={preview}"[:1000]
    return f"status_code={status_code}"


def _field_text(fields: dict[str, Any]) -> str:
    merged = {**current_trace_fields(), **fields}
    parts = []
    for key, value in merged.items():
        if value is None:
            continue
        parts.append(f"{key}={_clean_value(value)}")
    return " | ".join(parts)


def log_timing(
    component: str,
    operation: str,
    duration_ms: float,
    *,
    status: str = "success",
    log=None,
    **fields: Any,
) -> None:
    api_hint = fields.get("api_name") or operation
    if component != "external_api" or not _is_tracked_api(api_hint):
        return

    target_logger = log or logger
    extra = _field_text(fields)
    suffix = f" | {extra}" if extra else ""
    target_logger.info(
        f"[TIMING] component={component} | operation={operation} | "
        f"duration_ms={duration_ms:.2f} | status={status}{suffix}"
    )


def endpoint_from_url(url: str) -> str:
    try:
        parsed = urlsplit(str(url))
        if parsed.path:
            return parsed.path[:255]
    except Exception:
        pass
    return str(url).split("?", 1)[0][:255]


async def _record_external_api_call_fallback(
    *,
    api_name: str,
    endpoint: str,
    method: str,
    success: bool,
    duration_ms: float,
    status_code: int | None,
    response_text: str | None,
    error: str | None,
) -> None:
    now = datetime.now(timezone.utc)
    status_codes = _status_codes_text(status_code)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ExternalApiDailyCount)
            .where(
                ExternalApiDailyCount.call_date == now.date(),
                ExternalApiDailyCount.api_name == api_name,
                ExternalApiDailyCount.method == method,
                ExternalApiDailyCount.endpoint == endpoint,
            )
            .with_for_update()
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = ExternalApiDailyCount(
                call_date=now.date(),
                api_name=api_name,
                method=method,
                endpoint=endpoint,
                total_calls=1,
                success_calls=1 if success else 0,
                failure_calls=0 if success else 1,
                total_duration_ms=duration_ms,
                max_duration_ms=duration_ms,
                last_status_code=status_code,
                status_codes=status_codes,
                last_response=response_text,
                last_error=error,
                error_messages=error,
                last_called_at=now,
            )
            db.add(row)
        else:
            row.total_calls += 1
            row.success_calls += 1 if success else 0
            row.failure_calls += 0 if success else 1
            row.total_duration_ms += duration_ms
            row.max_duration_ms = max(float(row.max_duration_ms or 0), duration_ms)
            row.last_status_code = status_code
            row.status_codes = _append_distinct_csv(row.status_codes, status_codes)
            row.last_response = response_text
            row.last_error = error
            row.error_messages = _append_distinct_messages(row.error_messages, error)
            row.last_called_at = now
            row.updated_at = now
        await db.commit()


async def record_external_api_call(
    *,
    api_name: str,
    endpoint: str = "",
    method: str = "",
    success: bool,
    duration_ms: float,
    status_code: int | None = None,
    response_text: str | None = None,
    error: str | None = None,
) -> None:
    api_name = str(api_name or "unknown")[:100]
    if not _is_tracked_api(api_name):
        return

    endpoint = str(endpoint or "")[:255]
    method = str(method or "").upper()[:16]
    duration_ms = float(duration_ms or 0.0)
    response_text = (
        str(response_text)[:MAX_STORED_RESPONSE_CHARS] if response_text else None
    )
    error = str(error)[:1000] if error else None
    status_codes = _status_codes_text(status_code)
    now = datetime.now(timezone.utc)

    try:
        async with AsyncSessionLocal() as db:
            bind = db.get_bind()
            if bind.dialect.name != "postgresql":
                raise RuntimeError("non-postgresql dialect")

            stmt = pg_insert(ExternalApiDailyCount).values(
                call_date=now.date(),
                api_name=api_name,
                endpoint=endpoint,
                method=method,
                total_calls=1,
                success_calls=1 if success else 0,
                failure_calls=0 if success else 1,
                total_duration_ms=duration_ms,
                max_duration_ms=duration_ms,
                last_status_code=status_code,
                status_codes=status_codes,
                last_response=response_text,
                last_error=error,
                error_messages=error,
                last_called_at=now,
                created_at=now,
                updated_at=now,
            )
            update_values = {
                "total_calls": ExternalApiDailyCount.total_calls + 1,
                "success_calls": ExternalApiDailyCount.success_calls + (1 if success else 0),
                "failure_calls": ExternalApiDailyCount.failure_calls + (0 if success else 1),
                "total_duration_ms": ExternalApiDailyCount.total_duration_ms + duration_ms,
                "max_duration_ms": func.greatest(
                    ExternalApiDailyCount.max_duration_ms,
                    duration_ms,
                ),
                "last_status_code": status_code,
                "status_codes": func.concat_ws(
                    ",",
                    ExternalApiDailyCount.status_codes,
                    status_codes,
                ),
                "last_response": response_text,
                "last_error": error,
                "error_messages": func.left(
                    func.concat_ws(
                        "\n---\n",
                        ExternalApiDailyCount.error_messages,
                        error,
                    ),
                    4000,
                ),
                "last_called_at": now,
                "updated_at": now,
            }
            stmt = stmt.on_conflict_do_update(
                index_elements=["call_date", "api_name", "method", "endpoint"],
                set_=update_values,
            )
            await db.execute(stmt)
            await db.commit()
            return
    except Exception as exc:
        try:
            await _record_external_api_call_fallback(
                api_name=api_name,
                endpoint=endpoint,
                method=method,
                success=success,
                duration_ms=duration_ms,
                status_code=status_code,
                response_text=response_text,
                error=error,
            )
        except Exception:
            logger.warning(
                "[OBSERVABILITY] failed to update external_api_daily_counts | "
                f"api_name={api_name} | error={type(exc).__name__}",
                exc_info=True,
            )


def _status_success(status_code: int | None, success_statuses: Iterable[int] | None) -> bool:
    if status_code is None:
        return False
    if success_statuses is not None:
        return status_code in set(success_statuses)
    return 200 <= status_code < 400


async def timed_httpx_request(
    client,
    method: str,
    url: str,
    *,
    api_name: str,
    endpoint: str | None = None,
    success_statuses: Iterable[int] | None = None,
    log=None,
    **kwargs: Any,
):
    method = method.upper()
    endpoint = endpoint or endpoint_from_url(url)
    start = time.perf_counter()
    response = None
    status_code = None
    success = False
    error = None
    try:
        response = await client.request(method, url, **kwargs)
        status_code = response.status_code
        success = _success_from_response(response, success_statuses)
        return response
    except Exception as exc:
        error = type(exc).__name__
        raise
    finally:
        duration_ms = _elapsed_ms(start)
        response_text = _response_preview(response)
        if error:
            success = False
        response_error = error or _error_from_response(response, success)
        log_timing(
            "external_api",
            api_name,
            duration_ms,
            status="success" if success else "error",
            log=log,
            method=method,
            endpoint=endpoint,
            status_code=status_code,
            response=response_text,
            error=response_error,
        )
        await record_external_api_call(
            api_name=api_name,
            endpoint=endpoint,
            method=method,
            success=success,
            duration_ms=duration_ms,
            status_code=status_code,
            response_text=response_text,
            error=response_error,
        )
        feature_event = API_FEATURE_EVENTS.get(api_name)
        if feature_event:
            await record_feature_result(
                feature_event,
                success=success,
                reason=response_error,
            )


async def timed_requests_request(
    method: str,
    url: str,
    *,
    api_name: str,
    endpoint: str | None = None,
    success_statuses: Iterable[int] | None = None,
    log=None,
    **kwargs: Any,
):
    import requests

    method = method.upper()
    endpoint = endpoint or endpoint_from_url(url)
    start = time.perf_counter()
    response = None
    status_code = None
    success = False
    error = None
    try:
        response = requests.request(method, url, **kwargs)
        status_code = response.status_code
        success = _success_from_response(response, success_statuses)
        return response
    except Exception as exc:
        error = type(exc).__name__
        raise
    finally:
        duration_ms = _elapsed_ms(start)
        response_text = _response_preview(response)
        if error:
            success = False
        response_error = error or _error_from_response(response, success)
        log_timing(
            "external_api",
            api_name,
            duration_ms,
            status="success" if success else "error",
            log=log,
            method=method,
            endpoint=endpoint,
            status_code=status_code,
            response=response_text,
            error=response_error,
        )
        await record_external_api_call(
            api_name=api_name,
            endpoint=endpoint,
            method=method,
            success=success,
            duration_ms=duration_ms,
            status_code=status_code,
            response_text=response_text,
            error=response_error,
        )
        feature_event = API_FEATURE_EVENTS.get(api_name)
        if feature_event:
            await record_feature_result(
                feature_event,
                success=success,
                reason=response_error,
            )
