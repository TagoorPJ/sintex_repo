from __future__ import annotations

import os
import json
import httpx
from dotenv import load_dotenv
from langchain.tools import tool

from app.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

BASE_URL = os.getenv("EVOLVE_API_URL", "")
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


def _json_response(status: str, message: str, data: dict = None):
    payload = {
        "status": status,
        "message": message
    }

    if data:
        payload.update(data)

    return json.dumps(payload, ensure_ascii=False)


def _safe_int(value):
    try:
        return int(float(value))
    except Exception:
        return None


def _safe_float(value):
    try:
        return float(value)
    except Exception:
        return None


@tool("create_claim_tool")
async def create_claim_tool(
    user_id_evolve: str,
    retailerMerchantId: str,
    purchase_value: str
) -> str:
    """
    Tool Name: create_claim_tool

    Use ONLY after dealer selection + purchase value collected.

    Inputs:
    - user_id_evolve
    - retailerMerchantId (dealer_code)
    - purchase_value
    """

    user_id = _safe_int(user_id_evolve)
    amount = _safe_float(purchase_value)

    if not user_id:
        return _json_response(
            "error",
            "Valid user ID required."
        )

    if not retailerMerchantId or not str(retailerMerchantId).strip():
        return _json_response(
            "error",
            "Dealer code required."
        )

    if amount is None or amount <= 0:
        return _json_response(
            "error",
            "Valid purchase value required."
        )

    url = f"{BASE_URL}/claim/create"
    logger.info(f"url for creating claim: {url}")

    payload = {
        "user_id": user_id,
        "retailerMerchantId": retailerMerchantId,
        "purchaseValue": amount,
    }
    logger.info(f"Creating claim with payload: {payload}")

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(
                url,
                json=payload,
                headers=HEADERS
            )
        logger.info(f"Status Code: {response.status_code}")
        logger.info(f"Response Text: {response.text}")
        response.raise_for_status()

        if response.status_code != 201:
            return _json_response(
                "error",
                "Unable to create claim right now."
            )

        result = response.json()

        if result.get("status") != "success":
            return _json_response(
                "error",
                result.get("message", "Claim failed.")
            )

        return _json_response(
            "success",
            result.get("message", "Claim created successfully"),
            {
                "points_earned": result.get("points_earned", 0),
                "claim_id": result.get("claim_id")
            }
        )

    except httpx.TimeoutException:
        return _json_response(
            "error",
            "Request timed out while creating claim."
        )

    except Exception:
        logger.exception("[create_claim_tool] Unexpected Error")

        return _json_response(
            "error",
            "Something went wrong while creating claim."
        )