from __future__ import annotations

import argparse
import asyncio
import os
import smtplib
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from email.message import EmailMessage
from html import escape
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine


def find_project_root() -> Path:
    script_path = Path(__file__).resolve()
    for candidate in (script_path.parent, *script_path.parents):
        if (candidate / "alembic.ini").exists() and (candidate / "app").is_dir():
            return candidate
    for candidate in (script_path.parent, *script_path.parents):
        if (candidate / ".env").exists():
            return candidate
    return script_path.parents[1]


BASE_DIR = find_project_root()
load_dotenv(BASE_DIR / ".env")

DEFAULT_TIMEZONE = "Asia/Kolkata"
DEFAULT_SUBJECT_PREFIX = "Sintex Agent KPI Report"

RESPONSIVE_EMAIL_CSS = """
<style>
  @media only screen and (max-width: 640px) {
    .page {
      width: 100% !important;
      max-width: 100% !important;
      padding: 12px !important;
      box-sizing: border-box !important;
    }
    .hero {
      padding: 18px 16px !important;
      border-radius: 8px !important;
    }
    .hero-title {
      font-size: 22px !important;
      line-height: 1.25 !important;
    }
    .hero-copy {
      font-size: 12px !important;
      line-height: 1.45 !important;
    }
    .kpi-table,
    .kpi-table tbody,
    .kpi-table tr {
      display: block !important;
      width: 100% !important;
    }
    .kpi-cell {
      display: block !important;
      width: 100% !important;
      padding: 6px 0 !important;
      box-sizing: border-box !important;
    }
    .kpi-card {
      min-height: 0 !important;
      padding: 14px !important;
    }
    .section {
      padding: 14px !important;
      border-radius: 8px !important;
    }
    .desktop-table {
      display: none !important;
      max-height: 0 !important;
      overflow: hidden !important;
    }
    .mobile-records {
      display: block !important;
      max-height: none !important;
      overflow: visible !important;
    }
  }
</style>
"""

FLOW_API_MAP = {
    "evolve.register": "Registration",
    "evolve.validate_member": "Registration",
    "evolve.balance_inquiry": "My Rewards",
    "evolve.points_history": "My Rewards",
    "evolve.tier_status": "My Rewards",
    "evolve.reward_statement": "My Rewards",
    "evolve.find_dealer": "Upload Purchase",
    "evolve.capture_qr": "Upload Purchase",
    "evolve.claim_create": "Upload Purchase",
    "evolve.claim_status": "Upload Purchase",
    "evolve.support_ticket": "Support",
}

FLOW_COMPLETION_KPIS = {
    "evolve.register": {
        "name": "Completed Registrations",
        "flow": "Registration",
        "signal": "register API success response",
    },
    "evolve.balance_inquiry": {
        "name": "Reward Balance Checks",
        "flow": "My Rewards",
        "signal": "balance inquiry API success response",
    },
    "evolve.points_history": {
        "name": "Recent Transaction Views",
        "flow": "My Rewards",
        "signal": "points history API success response",
    },
    "evolve.tier_status": {
        "name": "Membership Tier Checks",
        "flow": "My Rewards",
        "signal": "tier status API success response",
    },
    "evolve.reward_statement": {
        "name": "Reward Statement Views",
        "flow": "My Rewards",
        "signal": "reward statement API success response",
    },
    "evolve.find_dealer": {
        "name": "Dealer List Loads",
        "flow": "Upload Purchase",
        "signal": "find dealer API success response",
    },
    "evolve.capture_qr": {
        "name": "QR Uploads Completed",
        "flow": "Upload Purchase",
        "signal": "capture QR API success or HTTP 200 response",
    },
    "evolve.claim_create": {
        "name": "Claims Created",
        "flow": "Upload Purchase",
        "signal": "claim create API success response",
    },
    "evolve.claim_status": {
        "name": "Claim Status Checks",
        "flow": "Upload Purchase",
        "signal": "claim status API success response",
    },
    "evolve.support_ticket": {
        "name": "Support Tickets Created",
        "flow": "Support",
        "signal": "support ticket API success response",
    },
}

KPI_DEFINITIONS = [
    ("Total Unique Users", "Distinct users who sent at least one message that day."),
    ("Total User Messages", "Total incoming user messages received that day."),
    ("Total Agent Messages", "Total assistant messages sent that day."),
    ("New Users Came", "User records created that day."),
    (
        "Completed Flow Actions",
        "Successful Evolve API calls that represent a completed user action.",
    ),
    ("Evolve API Hits", "Total tracked Evolve API requests made by this service."),
    (
        "Evolve API Failures",
        "Tracked Evolve requests that failed by exception, HTTP status, or response body.",
    ),
]


@dataclass
class DateWindow:
    start_day: date
    end_day: date
    timezone_name: str
    start_utc: datetime
    end_utc: datetime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Email daily Sintex Agent KPI report."
    )
    parser.add_argument(
        "--date",
        help="Report end date in YYYY-MM-DD. Defaults to today in --timezone.",
    )
    parser.add_argument(
        "--yesterday",
        action="store_true",
        help="Use yesterday in --timezone as the report end date.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of days to include ending at --date. Default: 1.",
    )
    parser.add_argument(
        "--timezone",
        default=os.getenv("KPI_REPORT_TIMEZONE", DEFAULT_TIMEZONE),
        help=f"Business timezone. Default: {DEFAULT_TIMEZONE}.",
    )
    parser.add_argument(
        "--to",
        help=(
            "Comma-separated recipients. Defaults to KPI_REPORT_TO, "
            "or KPI_EMAIL_TO."
        ),
    )
    parser.add_argument(
        "--subject-prefix",
        default=os.getenv("KPI_REPORT_SUBJECT_PREFIX", DEFAULT_SUBJECT_PREFIX),
        help=f"Email subject prefix. Default: {DEFAULT_SUBJECT_PREFIX}.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print report summary without sending email.",
    )
    return parser.parse_args()


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def resolve_timezone(timezone_name: str):
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        normalized = (timezone_name or "").strip().lower()
        if normalized in {"asia/kolkata", "asia/calcutta", "ist"}:
            return timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")
        if normalized in {"utc", "etc/utc"}:
            return timezone.utc
        raise


def build_window(args: argparse.Namespace) -> DateWindow:
    if args.days < 1:
        raise ValueError("--days must be at least 1")
    if args.date and args.yesterday:
        raise ValueError("Use either --date or --yesterday, not both")

    tz = resolve_timezone(args.timezone)
    if args.date:
        end_day = datetime.strptime(args.date, "%Y-%m-%d").date()
    elif args.yesterday:
        end_day = datetime.now(tz).date() - timedelta(days=1)
    else:
        end_day = datetime.now(tz).date()
    start_day = end_day - timedelta(days=args.days - 1)

    local_start = datetime.combine(start_day, time.min, tzinfo=tz)
    local_end = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=tz)

    return DateWindow(
        start_day=start_day,
        end_day=end_day,
        timezone_name=args.timezone,
        start_utc=local_start.astimezone(timezone.utc),
        end_utc=local_end.astimezone(timezone.utc),
    )


def day_range(window: DateWindow) -> list[date]:
    days = []
    current = window.start_day
    while current <= window.end_day:
        days.append(current)
        current += timedelta(days=1)
    return days


async def table_exists(conn, table_name: str) -> bool:
    return await conn.run_sync(
        lambda sync_conn: inspect(sync_conn).has_table(table_name)
    )


async def table_columns(conn, table_name: str) -> set[str]:
    return await conn.run_sync(
        lambda sync_conn: {
            column["name"]
            for column in inspect(sync_conn).get_columns(table_name)
        }
    )


async def fetch_all(conn, statement: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    result = await conn.execute(text(statement), params)
    return [dict(row._mapping) for row in result.fetchall()]


def _api_int(row: dict[str, Any], key: str) -> int:
    return int(row.get(key) or 0)


def aggregate_flow_completion_rows(api_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: dict[tuple[date, str], dict[str, Any]] = {}
    for row in api_rows:
        api_name = str(row.get("api_name") or "")
        definition = FLOW_COMPLETION_KPIS.get(api_name)
        if not definition:
            continue

        key = (row["day"], api_name)
        record = records.setdefault(
            key,
            {
                "day": row["day"],
                "api_name": api_name,
                "kpi_name": definition["name"],
                "flow": definition["flow"],
                "signal": definition["signal"],
                "total_calls": 0,
                "success_calls": 0,
                "failure_calls": 0,
            },
        )
        record["total_calls"] += _api_int(row, "total_calls")
        record["success_calls"] += _api_int(row, "success_calls")
        record["failure_calls"] += _api_int(row, "failure_calls")

    return sorted(
        records.values(),
        key=lambda item: (item["day"], item["flow"], item["kpi_name"]),
    )


def aggregate_flow_summary_rows(api_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for row in api_rows:
        api_name = str(row.get("api_name") or "")
        flow = FLOW_API_MAP.get(api_name, "Other Evolve API")
        record = records.setdefault(
            flow,
            {
                "flow": flow,
                "completed_actions": 0,
                "completion_attempts": 0,
                "total_calls": 0,
                "success_calls": 0,
                "failure_calls": 0,
                "action_names": set(),
                "apis_hit": set(),
            },
        )
        record["total_calls"] += _api_int(row, "total_calls")
        record["success_calls"] += _api_int(row, "success_calls")
        record["failure_calls"] += _api_int(row, "failure_calls")
        endpoint = str(row.get("endpoint") or "").strip()
        api_label = api_name
        if endpoint:
            api_label = f"{api_name} ({endpoint})"
        record["apis_hit"].add(api_label)

        definition = FLOW_COMPLETION_KPIS.get(api_name)
        if definition:
            record["completed_actions"] += _api_int(row, "success_calls")
            record["completion_attempts"] += _api_int(row, "total_calls")
            record["action_names"].add(definition["name"])

    rows = []
    for record in records.values():
        rows.append({
            **record,
            "action_names": ", ".join(sorted(record["action_names"])) or "-",
            "apis_hit": ", ".join(sorted(record["apis_hit"])) or "-",
        })
    return sorted(rows, key=lambda item: item["flow"])


async def load_report_data(database_url: str, window: DateWindow) -> dict[str, Any]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            daily_rows = await fetch_all(
                conn,
                """
                SELECT
                    (created_at AT TIME ZONE :tz)::date AS day,
                    COUNT(DISTINCT user_id) FILTER (WHERE sender = 'user') AS unique_users,
                    COUNT(*) FILTER (WHERE sender = 'user') AS user_messages,
                    COUNT(*) FILTER (WHERE sender = 'assistant') AS assistant_messages,
                    COUNT(*) AS total_messages
                FROM messages
                WHERE created_at >= :start_utc
                  AND created_at < :end_utc
                GROUP BY day
                ORDER BY day
                """,
                {
                    "tz": window.timezone_name,
                    "start_utc": window.start_utc,
                    "end_utc": window.end_utc,
                },
            )

            new_user_rows = await fetch_all(
                conn,
                """
                SELECT
                    (created_at AT TIME ZONE :tz)::date AS day,
                    COUNT(*) AS new_users,
                    COUNT(*) FILTER (
                        WHERE user_id_evolve IS NOT NULL
                          AND user_id_evolve NOT IN ('', 'null', 'none', 'undefined')
                    ) AS new_users_with_evolve_id
                FROM users
                WHERE created_at >= :start_utc
                  AND created_at < :end_utc
                GROUP BY day
                ORDER BY day
                """,
                {
                    "tz": window.timezone_name,
                    "start_utc": window.start_utc,
                    "end_utc": window.end_utc,
                },
            )

            api_rows: list[dict[str, Any]] = []
            if await table_exists(conn, "external_api_daily_counts"):
                api_columns = await table_columns(conn, "external_api_daily_counts")
                status_codes_select = (
                    "status_codes"
                    if "status_codes" in api_columns
                    else "NULL::text AS status_codes"
                )
                error_messages_select = (
                    "error_messages"
                    if "error_messages" in api_columns
                    else "NULL::text AS error_messages"
                )
                api_rows = await fetch_all(
                    conn,
                    f"""
                    SELECT
                        call_date AS day,
                        api_name,
                        method,
                        endpoint,
                        total_calls,
                        success_calls,
                        failure_calls,
                        total_duration_ms,
                        max_duration_ms,
                        last_status_code,
                        last_error,
                        {status_codes_select},
                        {error_messages_select}
                    FROM external_api_daily_counts
                    WHERE call_date >= :start_day
                      AND call_date <= :end_day
                    ORDER BY call_date, api_name, method, endpoint
                    """,
                    {
                        "start_day": window.start_day,
                        "end_day": window.end_day,
                    },
                )

    finally:
        await engine.dispose()

    return {
        "daily_rows": daily_rows,
        "new_user_rows": new_user_rows,
        "api_rows": api_rows,
    }


def index_by_day(rows: list[dict[str, Any]]) -> dict[date, dict[str, Any]]:
    return {row["day"]: row for row in rows}


def fmt_int(value: Any) -> str:
    return f"{int(value or 0):,}"


def fmt_ms(value: Any) -> str:
    return f"{float(value or 0):,.2f} ms"


def pct(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.0%"
    return f"{(numerator / denominator) * 100:.1f}%"


def average_ms(total_duration_ms: Any, total_calls: Any) -> float:
    calls = int(total_calls or 0)
    if calls <= 0:
        return 0.0
    return float(total_duration_ms or 0.0) / calls


def format_status_codes(row: dict[str, Any]) -> str:
    values = set()
    raw_codes = str(row.get("status_codes") or "")
    for item in raw_codes.replace("\n", ",").split(","):
        code = item.strip()
        if code and code.lower() not in {"none", "null"}:
            values.add(code)
    last_status_code = row.get("last_status_code")
    if last_status_code is not None:
        values.add(str(last_status_code))
    if not values:
        return "-"
    return ", ".join(sorted(values, key=lambda value: (not value.isdigit(), value)))


def format_error_messages(row: dict[str, Any]) -> str:
    raw_errors = row.get("error_messages") or row.get("last_error") or ""
    seen = set()
    errors = []
    for item in str(raw_errors).split("\n---\n"):
        message = " ".join(item.split())
        if not message or message in seen:
            continue
        seen.add(message)
        errors.append(message[:220])
    if not errors:
        return "-"
    suffix = "" if len(errors) <= 3 else f" (+{len(errors) - 3} more)"
    return "; ".join(errors[:3]) + suffix


def td(value: Any, *, align: str = "left") -> str:
    return (
        f'<td style="padding:10px;border-bottom:1px solid #e5e7eb;'
        f'text-align:{align};vertical-align:top;line-height:1.35;'
        f'word-break:break-word;">{escape(str(value))}</td>'
    )


def th(value: str, *, align: str = "left") -> str:
    return (
        f'<th style="padding:10px;border-bottom:1px solid #d1d5db;'
        f'text-align:{align};font-size:12px;color:#374151;'
        f'vertical-align:bottom;line-height:1.35;">{escape(value)}</th>'
    )


def render_mobile_records(headers: list[tuple[str, str]], rows: list[list[Any]]) -> str:
    cards = []
    for row in rows:
        pairs = []
        for value, (label, align) in zip(row, headers):
            value_align = "right" if align == "right" else "left"
            pairs.append(
                "<tr>"
                '<td style="padding:7px 0;color:#6b7280;font-size:12px;'
                'line-height:1.35;vertical-align:top;width:42%;">'
                f"{escape(label)}"
                "</td>"
                f'<td style="padding:7px 0;color:#111827;font-size:13px;'
                f'font-weight:600;line-height:1.35;text-align:{value_align};'
                f'vertical-align:top;word-break:break-word;">'
                f"{escape(str(value))}"
                "</td>"
                "</tr>"
            )
        cards.append(
            '<div style="border:1px solid #e5e7eb;border-radius:8px;'
            'padding:12px;margin-top:10px;background:#ffffff;">'
            '<table role="presentation" style="width:100%;border-collapse:collapse;">'
            f"{''.join(pairs)}"
            "</table>"
            "</div>"
        )
    return (
        '<div class="mobile-records" style="display:none;mso-hide:all;">'
        f"{''.join(cards)}"
        "</div>"
    )


def render_table(headers: list[tuple[str, str]], rows: list[list[Any]]) -> str:
    if not rows:
        return '<p style="color:#6b7280;margin:8px 0 0;">No records for this period.</p>'
    header_html = "".join(th(label, align=align) for label, align in headers)
    body_html = []
    for row in rows:
        cells = []
        for value, (_, align) in zip(row, headers):
            cells.append(td(value, align=align))
        body_html.append("<tr>" + "".join(cells) + "</tr>")
    min_width = max(520, len(headers) * 110)
    return (
        '<div class="desktop-table" style="width:100%;overflow-x:auto;'
        '-webkit-overflow-scrolling:touch;">'
        f'<table style="width:100%;min-width:{min_width}px;'
        'border-collapse:collapse;font-size:13px;">'
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{''.join(body_html)}</tbody>"
        "</table>"
        "</div>"
        f"{render_mobile_records(headers, rows)}"
    )


def render_kpi_card(label: str, value: str) -> str:
    return f"""
    <td class="kpi-cell" style="width:50%;padding:8px;vertical-align:top;">
      <div class="kpi-card" style="border:1px solid #e5e7eb;border-radius:8px;padding:14px;background:#ffffff;min-height:74px;box-sizing:border-box;">
        <div style="font-size:13px;color:#4b5563;margin-bottom:8px;line-height:1.3;">{escape(label)}</div>
        <div style="font-size:24px;font-weight:700;color:#111827;line-height:1.15;">{escape(value)}</div>
      </div>
    </td>
    """


def build_report_html(report: dict[str, Any], window: DateWindow) -> str:
    daily_by_day = index_by_day(report["daily_rows"])
    new_users_by_day = index_by_day(report["new_user_rows"])
    api_rows = report["api_rows"]
    completion_rows = aggregate_flow_completion_rows(api_rows)
    flow_summary_rows = aggregate_flow_summary_rows(api_rows)

    totals = {
        "unique_users": 0,
        "user_messages": 0,
        "assistant_messages": 0,
        "new_users": 0,
        "completed_flow_actions": 0,
        "api_calls": 0,
        "api_success": 0,
        "api_failure": 0,
    }

    for day in day_range(window):
        daily = daily_by_day.get(day, {})
        new_users = new_users_by_day.get(day, {})
        totals["unique_users"] += int(daily.get("unique_users") or 0)
        totals["user_messages"] += int(daily.get("user_messages") or 0)
        totals["assistant_messages"] += int(daily.get("assistant_messages") or 0)
        totals["new_users"] += int(new_users.get("new_users") or 0)

    for row in api_rows:
        totals["api_calls"] += int(row.get("total_calls") or 0)
        totals["api_success"] += int(row.get("success_calls") or 0)
        totals["api_failure"] += int(row.get("failure_calls") or 0)

    for row in completion_rows:
        totals["completed_flow_actions"] += int(row.get("success_calls") or 0)

    definition_table_rows = [
        [name, description] for name, description in KPI_DEFINITIONS
    ]

    daily_table_rows = []
    for day in day_range(window):
        daily = daily_by_day.get(day, {})
        new_users = new_users_by_day.get(day, {})
        daily_table_rows.append([
            day.isoformat(),
            fmt_int(daily.get("unique_users")),
            fmt_int(daily.get("user_messages")),
            fmt_int(daily.get("assistant_messages")),
            fmt_int(new_users.get("new_users")),
        ])

    flow_summary_table_rows = []
    for row in flow_summary_rows:
        total = int(row.get("total_calls") or 0)
        success = int(row.get("success_calls") or 0)
        attempts = int(row.get("completion_attempts") or 0)
        completed = int(row.get("completed_actions") or 0)
        flow_summary_table_rows.append([
            row.get("flow") or "",
            fmt_int(completed),
            fmt_int(attempts),
            fmt_int(total),
            fmt_int(success),
            fmt_int(row.get("failure_calls")),
            pct(success, total),
            row.get("apis_hit") or "-",
            row.get("action_names") or "-",
        ])

    completion_table_rows = []
    for row in completion_rows:
        attempts = int(row.get("total_calls") or 0)
        completed = int(row.get("success_calls") or 0)
        completion_table_rows.append([
            row["day"].isoformat(),
            row.get("kpi_name") or "",
            row.get("flow") or "",
            row.get("api_name") or "",
            fmt_int(completed),
            fmt_int(attempts),
            fmt_int(row.get("failure_calls")),
        ])

    api_health_table_rows = []
    for row in api_rows:
        total = int(row.get("total_calls") or 0)
        api_health_table_rows.append([
            row["day"].isoformat(),
            row.get("api_name") or "",
            row.get("method") or "",
            row.get("endpoint") or "",
            fmt_int(total),
            fmt_int(row.get("success_calls")),
            fmt_int(row.get("failure_calls")),
            fmt_ms(average_ms(row.get("total_duration_ms"), total)),
            fmt_ms(row.get("max_duration_ms")),
            format_status_codes(row),
            format_error_messages(row),
        ])

    period_label = (
        window.start_day.isoformat()
        if window.start_day == window.end_day
        else f"{window.start_day.isoformat()} to {window.end_day.isoformat()}"
    )
    title_label = f"Sintex Agent KPI Report for {period_label}"

    return f"""
<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  {RESPONSIVE_EMAIL_CSS}
</head>
<body style="margin:0;background:#eef2f7;font-family:Arial,Helvetica,sans-serif;color:#111827;-webkit-text-size-adjust:100%;">
  <div class="page" style="width:100%;max-width:980px;margin:0 auto;padding:20px;box-sizing:border-box;">
    <div class="hero" style="background:#111827;color:#ffffff;border-radius:8px;padding:22px 24px;">
      <div class="hero-copy" style="font-size:13px;color:#d1d5db;line-height:1.4;">{escape(window.timezone_name)}</div>
      <div class="hero-title" style="font-size:26px;font-weight:700;line-height:1.2;margin-top:4px;">{escape(title_label)}</div>
      <div class="hero-copy" style="font-size:13px;color:#d1d5db;line-height:1.45;margin-top:8px;">
        Daily usage, API-backed flow completions, and Evolve API health.
      </div>
    </div>

    <table class="kpi-table" role="presentation" style="width:100%;border-collapse:collapse;margin-top:14px;">
      <tr>
        {render_kpi_card("Total Unique Users", fmt_int(totals["unique_users"]))}
        {render_kpi_card("New Users Came", fmt_int(totals["new_users"]))}
      </tr>
      <tr>
        {render_kpi_card("Total User Messages", fmt_int(totals["user_messages"]))}
        {render_kpi_card("Total Agent Messages", fmt_int(totals["assistant_messages"]))}
      </tr>
      <tr>
        {render_kpi_card("Completed Flow Actions", fmt_int(totals["completed_flow_actions"]))}
        {render_kpi_card("Evolve API Hits", fmt_int(totals["api_calls"]))}
      </tr>
      <tr>
        {render_kpi_card("Evolve API Failures", fmt_int(totals["api_failure"]))}
      </tr>
    </table>

    <section class="section" style="background:#ffffff;border:1px solid #dfe5ee;border-radius:8px;padding:18px;margin-top:14px;">
      <h2 style="font-size:17px;line-height:1.3;margin:0 0 10px;">KPI Names</h2>
      {render_table(
        [
            ("KPI", "left"),
            ("What It Indicates", "left"),
        ],
        definition_table_rows,
      )}
    </section>

    <section class="section" style="background:#ffffff;border:1px solid #dfe5ee;border-radius:8px;padding:18px;margin-top:14px;">
      <h2 style="font-size:17px;line-height:1.3;margin:0 0 10px;">Daily KPI Summary</h2>
      {render_table(
        [
            ("Day", "left"),
            ("Total Unique Users", "right"),
            ("Total User Messages", "right"),
            ("Total Agent Messages", "right"),
            ("New Users Came", "right"),
        ],
        daily_table_rows,
      )}
    </section>

    <section class="section" style="background:#ffffff;border:1px solid #dfe5ee;border-radius:8px;padding:18px;margin-top:14px;">
      <h2 style="font-size:17px;line-height:1.3;margin:0 0 10px;">Flow Details Summary</h2>
      {render_table(
        [
            ("Flow", "left"),
            ("Completed Flow Actions", "right"),
            ("Completion Attempts", "right"),
            ("Evolve API Hits", "right"),
            ("Successful Hits", "right"),
            ("Evolve API Failures", "right"),
            ("Success %", "right"),
            ("APIs Hit", "left"),
            ("Tracked Action KPIs", "left"),
        ],
        flow_summary_table_rows,
      )}
    </section>

    <section class="section" style="background:#ffffff;border:1px solid #dfe5ee;border-radius:8px;padding:18px;margin-top:14px;">
      <h2 style="font-size:17px;line-height:1.3;margin:0 0 10px;">Flow Completion KPIs</h2>
      {render_table(
        [
            ("Day", "left"),
            ("KPI", "left"),
            ("Flow", "left"),
            ("Completion API", "left"),
            ("Completed", "right"),
            ("Attempts", "right"),
            ("Failed", "right"),
        ],
        completion_table_rows,
      )}
      <p style="font-size:12px;color:#6b7280;margin:10px 0 0;">
        Completed count uses successful Evolve API calls only. Failed attempts are shown separately.
      </p>
    </section>

    <section class="section" style="background:#ffffff;border:1px solid #dfe5ee;border-radius:8px;padding:18px;margin-top:14px;">
      <h2 style="font-size:17px;line-height:1.3;margin:0 0 10px;">Evolve API Health</h2>
      {render_table(
        [
            ("Day", "left"),
            ("API", "left"),
            ("Method", "left"),
            ("Endpoint", "left"),
            ("Total Hits", "right"),
            ("Successful Hits", "right"),
            ("Failed Hits", "right"),
            ("Average Time", "right"),
            ("Max Time", "right"),
            ("Status Codes", "left"),
            ("Errors", "left"),
        ],
        api_health_table_rows,
      )}
    </section>
  </div>
</body>
</html>
"""


def build_report_text(report: dict[str, Any], window: DateWindow) -> str:
    daily_by_day = index_by_day(report["daily_rows"])
    new_users_by_day = index_by_day(report["new_user_rows"])
    api_rows = report["api_rows"]
    completion_rows = aggregate_flow_completion_rows(api_rows)
    flow_summary_rows = aggregate_flow_summary_rows(api_rows)
    totals = {
        "unique_users": 0,
        "user_messages": 0,
        "assistant_messages": 0,
        "new_users": 0,
        "completed_flow_actions": 0,
        "api_calls": 0,
        "api_failure": 0,
    }

    for day in day_range(window):
        daily = daily_by_day.get(day, {})
        new_users = new_users_by_day.get(day, {})
        totals["unique_users"] += int(daily.get("unique_users") or 0)
        totals["user_messages"] += int(daily.get("user_messages") or 0)
        totals["assistant_messages"] += int(daily.get("assistant_messages") or 0)
        totals["new_users"] += int(new_users.get("new_users") or 0)

    for row in completion_rows:
        totals["completed_flow_actions"] += int(row.get("success_calls") or 0)

    for row in api_rows:
        totals["api_calls"] += int(row.get("total_calls") or 0)
        totals["api_failure"] += int(row.get("failure_calls") or 0)

    lines = [
        f"Sintex Agent KPI Report for {window.start_day} to {window.end_day} ({window.timezone_name})",
        "",
        "KPI Names:",
    ]
    for name, description in KPI_DEFINITIONS:
        lines.append(f"- {name}: {description}")

    lines.extend([
        "",
        "Top KPI Summary:",
        f"- Total Unique Users: {fmt_int(totals['unique_users'])}",
        f"- New Users Came: {fmt_int(totals['new_users'])}",
        f"- Total User Messages: {fmt_int(totals['user_messages'])}",
        f"- Total Agent Messages: {fmt_int(totals['assistant_messages'])}",
        f"- Completed Flow Actions: {fmt_int(totals['completed_flow_actions'])}",
        f"- Evolve API Hits: {fmt_int(totals['api_calls'])}",
        f"- Evolve API Failures: {fmt_int(totals['api_failure'])}",
        "",
        "Daily KPI Summary:",
    ])
    for day in day_range(window):
        daily = daily_by_day.get(day, {})
        new_users = new_users_by_day.get(day, {})
        lines.append(
            f"- {day}: total_unique_users={fmt_int(daily.get('unique_users'))}, "
            f"total_user_messages={fmt_int(daily.get('user_messages'))}, "
            f"total_agent_messages={fmt_int(daily.get('assistant_messages'))}, "
            f"new_users_came={fmt_int(new_users.get('new_users'))}"
        )

    lines.extend([
        "",
        "Flow Details Summary:",
    ])
    if not flow_summary_rows:
        lines.append("- No Evolve API-backed flow activity for this period.")
    for row in flow_summary_rows:
        total = int(row.get("total_calls") or 0)
        success = int(row.get("success_calls") or 0)
        lines.append(
            f"- {row['flow']}: completed_flow_actions="
            f"{fmt_int(row.get('completed_actions'))}, "
            f"completion_attempts={fmt_int(row.get('completion_attempts'))}, "
            f"evolve_api_hits={fmt_int(total)}, "
            f"successful_hits={fmt_int(success)}, "
            f"evolve_api_failures={fmt_int(row.get('failure_calls'))}, "
            f"success_rate={pct(success, total)}, "
            f"apis_hit={row.get('apis_hit') or '-'}, "
            f"tracked_action_kpis={row.get('action_names') or '-'}"
        )

    lines.append("")
    lines.append("Flow Completion KPIs:")
    if not completion_rows:
        lines.append("- No completed API-backed flow actions for this period.")
    for row in completion_rows:
        attempts = int(row.get("total_calls") or 0)
        completed = int(row.get("success_calls") or 0)
        lines.append(
            f"- {row['day']} {row['kpi_name']} ({row['flow']}): "
            f"completed={fmt_int(completed)}, attempts={fmt_int(attempts)}, "
            f"failed={fmt_int(row.get('failure_calls'))}"
        )

    lines.append("")
    lines.append("Evolve API Health:")
    if not api_rows:
        lines.append("- No Evolve API hits for this period.")
    for row in api_rows:
        total = int(row.get("total_calls") or 0)
        lines.append(
            f"- {row['day']} {row['api_name']} {row['endpoint']}: "
            f"total_hits={fmt_int(total)}, "
            f"successful_hits={fmt_int(row.get('success_calls'))}, "
            f"failed_hits={fmt_int(row.get('failure_calls'))}, "
            f"average_time={fmt_ms(average_ms(row.get('total_duration_ms'), total))}, "
            f"max_time={fmt_ms(row.get('max_duration_ms'))}, "
            f"status_codes={format_status_codes(row)}, "
            f"errors={format_error_messages(row)}"
        )
    return "\n".join(lines)


def send_email(
    *,
    recipients: list[str],
    subject: str,
    html_body: str,
    text_body: str,
) -> None:
    smtp_host = os.getenv("SMTP_HOST", "smtp.office365.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    sender = os.getenv("KPI_REPORT_FROM") or smtp_user

    if not recipients:
        raise RuntimeError(
            "No recipients configured. Set KPI_REPORT_TO or pass --to."
        )
    if not sender:
        raise RuntimeError("SMTP sender missing. Set SMTP_USER or KPI_REPORT_FROM.")
    if not smtp_user or not smtp_pass:
        raise RuntimeError("SMTP credentials missing. Set SMTP_USER and SMTP_PASS.")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as smtp:
            smtp.starttls()
            smtp.login(smtp_user, smtp_pass)
            smtp.send_message(message)
    except smtplib.SMTPRecipientsRefused as exc:
        refused = []
        for address, (code, reason) in exc.recipients.items():
            if isinstance(reason, bytes):
                reason = reason.decode("utf-8", errors="replace")
            refused.append(f"{address} ({code}: {reason})")
        hint = ""
        if any(address.lower().endswith("@example.com") for address in exc.recipients):
            hint = " Use a real recipient address; example.com is reserved for tests."
        raise RuntimeError(
            f"SMTP refused recipient(s): {', '.join(refused)}.{hint}"
        ) from exc
    except smtplib.SMTPAuthenticationError as exc:
        raise RuntimeError(
            "SMTP authentication failed. Check SMTP_USER and SMTP_PASS."
        ) from exc
    except smtplib.SMTPException as exc:
        raise RuntimeError(f"SMTP send failed: {exc}") from exc


async def async_main() -> None:
    args = parse_args()
    window = build_window(args)

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required to build the KPI report.")

    recipients = (
        split_csv(args.to)
        or split_csv(os.getenv("KPI_REPORT_TO"))
        or split_csv(os.getenv("KPI_EMAIL_TO"))
    )

    report = await load_report_data(database_url, window)
    html_body = build_report_html(report, window)
    text_body = build_report_text(report, window)

    subject_date = (
        window.start_day.isoformat()
        if window.start_day == window.end_day
        else f"{window.start_day.isoformat()} to {window.end_day.isoformat()}"
    )
    subject = f"{args.subject_prefix} - {subject_date}"

    if args.dry_run:
        print(text_body)
        print("")
        print(f"Recipients: {', '.join(recipients) if recipients else '(none)'}")
        print(f"Subject: {subject}")
        return

    send_email(
        recipients=recipients,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
    )
    print(f"KPI report sent to {', '.join(recipients)}")


def main() -> None:
    try:
        asyncio.run(async_main())
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
