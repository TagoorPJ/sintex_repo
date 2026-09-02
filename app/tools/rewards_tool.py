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
    "Authorization":os.getenv("EVOLVE_TOKEN")
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
    - "balance" → fetch current reward points balance
    - "history" → fetch recent transaction history
    - "tier" → fetch current tier and associated points

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

    Examples:

    Balance:
    {
    "action": "balance",
    "user_id_evolve": "<from COLLECTED_DATA>"
    }

    History:
    {
    "action": "history",
    "user_id_evolve": "<from COLLECTED_DATA>",
    "limit": 5,
    "offset": 1
    }

    Tier:
    {
    "action": "tier",
    "user_id_evolve": "<from COLLECTED_DATA>"
    }
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

            # # ── VALIDATE USER ─────────────────────────
            # validate_url = f"{BASE_URL}/validate"

            # validate_payload = {
            #     "mobile_number": mobile_number
            # }

            # validate_resp = await client.post(
            #     validate_url,
            #     json=validate_payload,
            #     headers=HEADERS
            # )
            # logger.info(f"[VALIDATE] Status={validate_resp.status_code} | response={validate_resp.text}")
            # validate_result = validate_resp.json()
            # is_valid = validate_result.get("is_valid")
            # user_status = validate_result.get("user_id_status")
            # logger.info(f"[VALIDATE CHECK] is_valid={is_valid} | user_id_status={user_status}")
            # if validate_resp.status_code != 200:
            #     return json.dumps({
            #         "status": "error",
            #         "message": "Unable to validate user."
            #     })

            # validate_result = validate_resp.json()

            # if not validate_result.get("is_valid") or validate_result.get("user_id_status") != "APPROVED":
            #     return json.dumps({
            #         "status": "error",
            #         "message": "Looks like you’re not active on Sintex Plumber Pride App yet. Don’t worry! Kindly reach out to our team for help."
            #     })

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

                return json.dumps({
                    "status": "success",
                    "message": f"Your current reward balance is {points} points."
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

                tier = result.get("tier", "N/A")
                points = result.get("points", 0)

                return json.dumps({
                    "status": "success",
                    "message": f"You are currently in {tier} tier with {points} points."
                })

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": "Something went wrong while fetching rewards data."
        })
