import json
import httpx
from typing import Dict, Any
from langchain.tools import tool
from dotenv import load_dotenv
import os
from app.utils.logger import get_logger  # adjust path
from app.utils.observability import timed_httpx_request

logger = get_logger(__name__)
load_dotenv()

BASE_URL = os.getenv("EVOLVE_API_URL")

HEADERS = {
    "accept": "*/*",
    "program": os.getenv("EVOLVE_PROGRAM"),
    "app": os.getenv("EVOLVE_APP"),
    "Content-Type": "application/json",
    "Authorization": os.getenv("EVOLVE_TOKEN")
}


def calculate_tier_info(points_val: Any) -> Dict[str, Any]:
    try:
        pts = float(points_val) if points_val is not None else 0.0
    except (ValueError, TypeError):
        pts = 0.0

    pts_display = int(pts) if pts.is_integer() else pts
    formatted_pts = f"{pts_display:,}" if isinstance(pts_display, int) else f"{pts_display:,.2f}"

    if pts < 5000:
        current_tier = "Bronze"
        next_tier = "Silver"
        target_pts = 5000
        needed = target_pts - pts
        needed_display = int(needed) if isinstance(needed, float) and needed.is_integer() else needed
        formatted_needed = f"{needed_display:,}" if isinstance(needed_display, int) else f"{needed_display:,.2f}"
        msg = (
            f"Your current reward balance is {formatted_pts} points. "
            f"You are currently in the Bronze tier. "
            f"You need {formatted_needed} more points to reach the Silver tier."
        )
        return {
            "points": pts_display,
            "current_tier": current_tier,
            "next_tier": next_tier,
            "points_needed_for_next_tier": needed_display,
            "message": msg,
        }
    elif pts < 35000:
        current_tier = "Silver"
        next_tier = "Gold"
        target_pts = 35000
        needed = target_pts - pts
        needed_display = int(needed) if isinstance(needed, float) and needed.is_integer() else needed
        formatted_needed = f"{needed_display:,}" if isinstance(needed_display, int) else f"{needed_display:,.2f}"
        msg = (
            f"Your current reward balance is {formatted_pts} points. "
            f"You are currently in the Silver tier. "
            f"You need {formatted_needed} more points to reach the Gold tier."
        )
        return {
            "points": pts_display,
            "current_tier": current_tier,
            "next_tier": next_tier,
            "points_needed_for_next_tier": needed_display,
            "message": msg,
        }
    elif pts < 85000:
        current_tier = "Gold"
        next_tier = "Platinum"
        target_pts = 85000
        needed = target_pts - pts
        needed_display = int(needed) if isinstance(needed, float) and needed.is_integer() else needed
        formatted_needed = f"{needed_display:,}" if isinstance(needed_display, int) else f"{needed_display:,.2f}"
        msg = (
            f"Your current reward balance is {formatted_pts} points. "
            f"You are currently in the Gold tier. "
            f"You need {formatted_needed} more points to reach the Platinum tier."
        )
        return {
            "points": pts_display,
            "current_tier": current_tier,
            "next_tier": next_tier,
            "points_needed_for_next_tier": needed_display,
            "message": msg,
        }
    else:
        current_tier = "Platinum"
        next_tier = None
        msg = (
            f"Your current reward balance is {formatted_pts} points. "
            f"You are currently in the Platinum tier (the highest tier)."
        )
        return {
            "points": pts_display,
            "current_tier": current_tier,
            "next_tier": next_tier,
            "points_needed_for_next_tier": 0,
            "message": msg,
        }


@tool("rewards_tool")
async def rewards_tool(
    action: str,
    user_id_evolve: str,
    mobile_number: str,
    limit: int = 10,
    offset: int = 1
) -> str:
    """
    Handles all user reward-related queries including balance, transaction history, and tier status.

    Use this tool whenever the user asks about:
    - reward points or balance
    - points history or transactions
    - tier, level, or status

    Supported actions:
    - "balance" → fetch current reward points balance and tier status
    - "history" → fetch recent transaction history
    - "tier" → fetch current tier, reward points balance, and points required for next tier

    Input requirements:
    Payload must be a valid JSON string containing:
    - action (string, required): one of "balance", "history", or "tier"
    - user_id_evolve (integer, required): must be taken from PREFILLED_DATA
    - limit (integer, optional): number of records for history (default: 5)
    - offset (integer, optional): pagination offset (default: 1)

    Strict rules:
    - Always include user_id_evolve from PREFILLED_DATA
    - Never ask the user for user_id_evolve
    - Never assume or generate user_id_evolve
    - Never call this tool without action and user_id_evolve
    - Do not pass null, empty, or invalid values
    - Always send clean JSON input

    When to call:
    - Immediately call the tool when the user asks about rewards, balance, transactions, or tier
    - Do not answer these queries manually

    Response behavior:
    - On success: returns JSON with "status": "success" and a user-friendly "message"
    - On failure: returns JSON with "status": "error" and an appropriate error message
    """
    logger.info(f"[VALIDATE] Calling API | mobile_number={mobile_number} | action={action}")
    # ── VALIDATION ───────────────────────────────
    if not user_id_evolve or not str(user_id_evolve).strip() or str(user_id_evolve).lower() in ["null", "none", "undefined"]:
        return json.dumps({
            "status": "error",
            "message": "User ID is required."
        })

    if action not in ["balance", "history", "tier"]:
        return json.dumps({
            "status": "error",
            "message": "Invalid action. Use: balance, history, or tier."
        })

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:

            # ── BALANCE API ─────────────────────────
            if action == "balance":
                url = f"{BASE_URL}/balance-inquiry"

                resp = await timed_httpx_request(
                    client,
                    "POST",
                    url,
                    api_name="evolve.balance_inquiry",
                    endpoint="/balance-inquiry",
                    log=logger,
                    json={"user_id": user_id_evolve},
                    headers=HEADERS
                )

                if resp.status_code != 200:
                    return json.dumps({
                        "status": "error",
                        "message": "Failed to fetch balance."
                    })

                result = resp.json()

                if result.get("status") != "success":
                    return json.dumps({
                        "status": "error",
                        "message": "Unable to fetch balance."
                    })

                points = result.get("points", 0)
                tier_info = calculate_tier_info(points)

                return json.dumps({
                    "status": "success",
                    "points": tier_info["points"],
                    "current_tier": tier_info["current_tier"],
                    "next_tier": tier_info["next_tier"],
                    "points_needed_for_next_tier": tier_info["points_needed_for_next_tier"],
                    "message": tier_info["message"],
                })

            # ── HISTORY API ─────────────────────────
            elif action == "history":
                url = f"{BASE_URL}/points-history"

                payload_data = {
                    "user_id": user_id_evolve,
                    "limit": limit,
                    "offset": offset
                }

                resp = await timed_httpx_request(
                    client,
                    "POST",
                    url,
                    api_name="evolve.points_history",
                    endpoint="/points-history",
                    log=logger,
                    json=payload_data,
                    headers=HEADERS
                )

                if resp.status_code != 200:
                    return json.dumps({
                        "status": "error",
                        "message": "Failed to fetch points history."
                    })

                result = resp.json()

                if result.get("status") != "success":
                    return json.dumps({
                        "status": "error",
                        "message": "Unable to fetch points history."
                    })

                transactions = result.get("transactions", [])
                if not transactions:
                    return json.dumps({
                        "status": "success",
                        "message": "No recent points history found."
                    })

                summary_lines = []

                for i, txn in enumerate(transactions[:5], start=1):
                    summary_lines.append(
                        f"{i})\n"
                        f"+{txn.get('points', 0)} points\n"
                        f"Type: {txn.get('trans_type', 'N/A')}\n"
                        f"Capture Mode: {txn.get('capture_type', 'N/A')}\n"
                        f"Category: {txn.get('gain_type', 'N/A')}\n"
                        f"Date: {txn.get('created_date', 'N/A')}\n"
                    )

                return json.dumps({
                    "status": "success",
                    "message": "Here is your recent points history:\n" + "\n".join(summary_lines)
                })

            # ── TIER API ────────────────────────────
            elif action == "tier":
                url = f"{BASE_URL}/tier-status"

                resp = await timed_httpx_request(
                    client,
                    "POST",
                    url,
                    api_name="evolve.tier_status",
                    endpoint="/tier-status",
                    log=logger,
                    json={"user_id": user_id_evolve},
                    headers=HEADERS
                )

                if resp.status_code != 200:
                    return json.dumps({
                        "status": "error",
                        "message": "Failed to fetch tier status."
                    })

                result = resp.json()

                if result.get("status") != "success":
                    return json.dumps({
                        "status": "error",
                        "message": "Unable to fetch tier status."
                    })

                points = result.get("points", 0)
                tier_info = calculate_tier_info(points)

                return json.dumps({
                    "status": "success",
                    "points": tier_info["points"],
                    "current_tier": tier_info["current_tier"],
                    "next_tier": tier_info["next_tier"],
                    "points_needed_for_next_tier": tier_info["points_needed_for_next_tier"],
                    "message": tier_info["message"],
                })

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": "Something went wrong while fetching rewards data."
        })
