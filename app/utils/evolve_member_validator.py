from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx
from dotenv import load_dotenv

from app.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)


@dataclass(frozen=True)
class MemberValidationResult:
    member_id: str | None
    is_valid: bool


class MemberValidationError(RuntimeError):
    """Raised when the Evolve validation service cannot be trusted."""


def _authorization_header() -> str:
    token = (os.getenv("EVOLVE_TOKEN") or "").strip()
    if not token:
        raise MemberValidationError("EVOLVE_TOKEN is not configured")
    if token.lower().startswith("bearer "):
        return token
    return f"Bearer {token}"


async def validate_member_by_mobile(mobile_number: str) -> MemberValidationResult:
    """Look up an Evolve member by mobile number without exposing credentials."""
    base_url = (os.getenv("EVOLVE_API_URL") or "").strip().rstrip("/")
    if not base_url:
        raise MemberValidationError("EVOLVE_API_URL is not configured")

    headers = {
        "accept": "*/*",
        "program": (os.getenv("EVOLVE_PROGRAM") or "1").strip(),
        "app": (os.getenv("EVOLVE_APP") or "PLUMBER").strip(),
        "Content-Type": "application/json",
        "Authorization": _authorization_header(),
    }
    payload = {"mobile_number": str(mobile_number).strip()}
    timeout = float(os.getenv("EVOLVE_TIMEOUT", "15"))

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{base_url}/validate",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data: Any = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.error(
            "[MEMBER VALIDATION] request failed | mobile=%s | error=%s",
            mobile_number,
            type(exc).__name__,
        )
        raise MemberValidationError("Evolve member validation failed") from exc

    if not isinstance(data, dict) or data.get("status") != "success":
        logger.error(
            "[MEMBER VALIDATION] invalid response | mobile=%s | status=%r",
            mobile_number,
            data.get("status") if isinstance(data, dict) else None,
        )
        raise MemberValidationError("Evolve member validation returned an invalid response")

    member_id = str(data.get("member_id") or "").strip()
    is_valid = bool(data.get("is_valid"))

    if is_valid and not member_id:
        logger.error(
            "[MEMBER VALIDATION] is_valid=true without member_id | mobile=%s",
            mobile_number,
        )
        raise MemberValidationError("Evolve validation response is inconsistent")

    logger.info(
        "[MEMBER VALIDATION] completed | mobile=%s | member_found=%s",
        mobile_number,
        bool(member_id),
    )
    return MemberValidationResult(
        member_id=member_id or None,
        is_valid=is_valid and bool(member_id),
    )
