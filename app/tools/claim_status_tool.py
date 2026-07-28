from __future__ import annotations

import os
import json
import httpx
from dotenv import load_dotenv
from langchain.tools import tool

from app.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

BASE_URL = os.getenv("EVOLVE_API_URL", "").rstrip("/")
PROGRAM = os.getenv("EVOLVE_PROGRAM")
APP_NAME = os.getenv("EVOLVE_APP")
AUTH_TOKEN = os.getenv("EVOLVE_TOKEN")
REQUEST_TIMEOUT = float(os.getenv("EVOLVE_TIMEOUT", "15"))

HEADERS = {
    "accept": "*/*",
    "program": PROGRAM,
    "app": APP_NAME,
    "Content-Type": "application/json",
    "Authorization": AUTH_TOKEN,
}


def _json_response(status: str, message: str, data: dict = None) -> str:
    payload = {"status": status, "message": message}
    if data:
        payload.update(data)
    return json.dumps(payload, ensure_ascii=False)


def _safe_int(value) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


@tool("claim_status_tool")
async def claim_status_tool(
    user_id_evolve: str,
    invoice_id: str,
) -> str:
    """
    Tool Name: claim_status_tool

    Purpose:
    Use this tool to check the status of a previously submitted claim / purchase.

    Use this tool whenever the user asks about:
    - claim status
    - check my claim
    - status of my purchase
    - did my claim get approved
    - points from claim
    - points added for my invoice
    - claim confirmation

    Parameters Accepted:

    1. user_id_evolve (Required)
       - Type: string / integer
       - Source: MUST come from PREFILLED_DATA
       - Never ask the user for this

    2. invoice_id (Required)
       - Type: string
       - Example: ABCD123456
       - The invoice/claim reference number
       - You MUST ask the user to provide this if not already given

    Mandatory Execution Rules:
    - Always call this tool when user asks for claim status
    - user_id_evolve must come from PREFILLED_DATA — never ask the user
    - invoice_id must be collected from the user before calling this tool
    - Never assume or fabricate invoice_id

    Success Response Format:
    {
        "status": "success",
        "message": "User-friendly claim status message",
        "points_added": <float>,
        "claim_status": "<PENDING|APPROVED|REJECTED>"
    }

    Error Response Format:
    {
        "status": "error",
        "message": "Reason for failure"
    }

    When to Trigger Examples:
    - Check my claim status
    - What is the status of invoice ABCD123456
    - Did my claim get approved
    - How many points for my claim
    """

    logger.info(
        f"[claim_status_tool] Called | user_id={user_id_evolve} | invoice_id={invoice_id}"
    )

    # ── Validate user_id ────────────────────────────────────────
    user_id = _safe_int(user_id_evolve)

    if not user_id:
        return _json_response("error", "Valid user ID is required.")

    # ── Validate invoice_id ─────────────────────────────────────
    invoice_id = str(invoice_id).strip() if invoice_id else ""
    if not invoice_id:
        return _json_response("error", "Invoice ID is required to check claim status.")

    # ── API Call ────────────────────────────────────────────────
    url = f"{BASE_URL}/claim-points-confirmation"
    payload = {
        "user_id": user_id,
        "invoice_id": invoice_id,
    }

    logger.info(f"[claim_status_tool] Calling Evolve API | payload={payload}")

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(url, json=payload, headers=HEADERS)

        logger.info(f"[claim_status_tool] API Status={response.status_code}")

        if response.status_code == 404:
            return _json_response(
                "error",
                f"No claim found for invoice ID: {invoice_id}. Please verify and try again.",
            )

        if response.status_code != 200:
            logger.error(
                f"[claim_status_tool] Non-200 response: {response.status_code} | {response.text}"
            )
            return _json_response(
                "error", "Unable to fetch claim status right now. Please try again later."
            )

        result = response.json()
        logger.info(f"[claim_status_tool] API Response={result}")

        if result.get("status") != "success":
            return _json_response(
                "error",
                result.get("message", "Claim status not available."),
            )

        points_added = result.get("points_added", 0.0)
        claim_status = result.get("claim_status", "UNKNOWN")

        # ── Build user-friendly message ──────────────────────────
        status_emoji = {
            "APPROVED": "✅",
            "PENDING": "⏳",
            "REJECTED": "❌",
        }.get(claim_status.upper(), "ℹ️")

        message = (
            f"{status_emoji} Claim Status for Invoice: {invoice_id}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📌 Status       : {claim_status}\n"
            f"⭐ Points Added : {points_added:.0f}\n\n"
            f"Please contact Sintex Sales employee."
        )

        return _json_response(
            "success",
            message,
            {
                "points_added": points_added,
                "claim_status": claim_status,
                "invoice_id": invoice_id,
            },
        )

    except httpx.TimeoutException:
        logger.error("[claim_status_tool] Request timed out")
        return _json_response(
            "error", "Request timed out while checking claim status. Please try again."
        )

    except Exception:
        logger.exception("[claim_status_tool] Unexpected error")
        return _json_response(
            "error", "Something went wrong while checking claim status."
        )