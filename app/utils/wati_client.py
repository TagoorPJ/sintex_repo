"""
app/utils/wati_client.py

Thin async wrapper around the WATI sendSessionFile endpoint.

Used to push generated PDFs (e.g. reward statements) to the user's
WhatsApp during an open 24-hour session window.

Why async/httpx instead of `requests`:
The rest of the codebase is async (FastAPI + httpx). Calling sync
`requests` inside an async handler would block the event loop. We use
httpx to stay consistent.

Required environment variables:
  WATI_LINK     — base URL of the WATI tenant, e.g.
                  "https://live-mt-server.wati.io/<tenant>/" (must end with /)
  BEARER_TOKEN  — Authorization header value, e.g. "Bearer eyJhbGciOi..."
                  (include the word "Bearer " if WATI requires it; copy
                  the exact value WATI gives you).
"""

from __future__ import annotations

import os
from typing import Optional

import httpx

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Allow long upload time for medium-sized PDFs over slow connections.
WATI_TIMEOUT = float(os.getenv("WATI_TIMEOUT", "60"))


async def send_session_document(
    *,
    file_path: str,
    file_name: str,
    phone: str,
    caption: Optional[str] = None,
) -> dict:
    """
    Send a file to the user's WhatsApp via WATI's sendSessionFile API.

    Args:
        file_path:  absolute path to the file on disk
        file_name:  the name the recipient sees (e.g. "reward_statement_april.pdf")
        phone:      recipient phone number (digits only, country code first)
        caption:    optional WhatsApp caption shown above the file

    Returns:
        {
          "ok":      bool,
          "status":  int | None,       # HTTP status code from WATI (None on transport error)
          "message": str,              # human-readable summary
          "raw":     dict | None,      # parsed JSON body when available
        }
    """

    base = (os.getenv("WATI_LINK") or "").strip()
    token = (os.getenv("BEARER_TOKEN") or "").strip()

    if not base:
        logger.error("[wati_client] WATI_LINK not configured")
        return {"ok": False, "status": None, "message": "WATI_LINK not configured", "raw": None}
    if not token:
        logger.error("[wati_client] BEARER_TOKEN not configured")
        return {"ok": False, "status": None, "message": "BEARER_TOKEN not configured", "raw": None}

    if not os.path.exists(file_path):
        logger.error(f"[wati_client] File not found: {file_path}")
        return {"ok": False, "status": None, "message": "File not found", "raw": None}

    # Phone must contain digits only — strip "+", spaces, dashes.
    clean_phone = "".join(c for c in str(phone) if c.isdigit())
    if not clean_phone:
        return {"ok": False, "status": None, "message": "Invalid phone number", "raw": None}

    # WATI requires international format (country code + number, no "+").
    # If the caller passed a bare 10-digit Indian number, prepend "91".
    # We only do this for exactly-10-digit numbers so we don't accidentally
    # mangle other-country numbers or already-formatted ones.
    if len(clean_phone) == 10:
        logger.info(
            f"[wati_client] 10-digit number {clean_phone} received; "
            "prepending Indian country code 91"
        )
        clean_phone = "91" + clean_phone

    # WATI accepts caption as a query string parameter on this endpoint.
    base_clean = base if base.endswith("/") else base + "/"
    url = f"{base_clean}api/v1/sendSessionFile/{clean_phone}"
    params = {"caption": caption} if caption else None

    headers = {"Authorization": token}

    logger.info(f"[wati_client] POST {url} | file={file_name} | phone={clean_phone}")

    try:
        async with httpx.AsyncClient(timeout=WATI_TIMEOUT, verify=False) as client:
            with open(file_path, "rb") as fh:
                files = {"file": (file_name, fh, "application/pdf")}
                resp = await client.post(
                    url,
                    params=params,
                    headers=headers,
                    files=files,
                )
    except httpx.TimeoutException:
        logger.error("[wati_client] Timeout sending file to WATI")
        return {"ok": False, "status": None, "message": "WATI request timed out", "raw": None}
    except Exception as exc:
        logger.exception("[wati_client] Unexpected error sending file to WATI")
        return {"ok": False, "status": None, "message": f"WATI error: {exc}", "raw": None}

    body = None
    try:
        body = resp.json()
    except Exception:
        body = None

    logger.info(
        f"[wati_client] WATI response | status={resp.status_code} | "
        f"body={(resp.text[:300] if resp.text else '')}"
    )

    # WATI returns 200 + {"result": True} on success. Some tenants return
    # a `success` or `ok` boolean — accept any truthy success indicator.
    is_ok = resp.status_code == 200
    if isinstance(body, dict):
        for key in ("result", "success", "ok"):
            if key in body:
                is_ok = is_ok and bool(body.get(key))
                break

    # Extract a human-readable failure reason from the WATI body.
    if not is_ok and isinstance(body, dict):
        wati_msg = body.get("message", "")
        ticket_status = body.get("ticketStatus", "")
        if ticket_status == "EXPIRED":
            failure_reason = "WATI session expired — user must send a message first to reopen the 24h window"
        elif wati_msg:
            failure_reason = wati_msg
        else:
            failure_reason = f"WATI returned status {resp.status_code}"
        logger.error(f"[wati_client] Send failed: {failure_reason}")
    else:
        failure_reason = f"WATI returned status {resp.status_code}"

    return {
        "ok": is_ok,
        "status": resp.status_code,
        "message": "Document sent to WhatsApp" if is_ok else failure_reason,
        "raw": body,
    }


async def send_session_image(
    *,
    file_bytes: Optional[bytes] = None,
    file_path: Optional[str] = None,
    file_name: str = "greeting.jpg",
    phone: str,
    caption: Optional[str] = None,
) -> dict:
    """
    Send an image directly to the user's WhatsApp chat via WATI's sendSessionFile API.
    Can accept either raw bytes (in memory) or a file path on disk.
    """
    base = (os.getenv("WATI_LINK") or "").strip()
    token = (os.getenv("BEARER_TOKEN") or os.getenv("WATI_TOKEN") or "").strip().strip('"').strip("'")
    if token and not token.lower().startswith("bearer "):
        token = f"Bearer {token}"

    if not base:
        logger.error("[wati_client] WATI_LINK not configured")
        return {"ok": False, "status": None, "message": "WATI_LINK not configured", "raw": None}
    if not token:
        logger.error("[wati_client] BEARER_TOKEN not configured")
        return {"ok": False, "status": None, "message": "BEARER_TOKEN not configured", "raw": None}

    if file_bytes is None:
        if not file_path or not os.path.exists(file_path):
            logger.error(f"[wati_client] File not found: {file_path}")
            return {"ok": False, "status": None, "message": "File not found", "raw": None}
        with open(file_path, "rb") as fh:
            content = fh.read()
    else:
        content = file_bytes

    clean_phone = "".join(c for c in str(phone) if c.isdigit())
    if not clean_phone:
        return {"ok": False, "status": None, "message": "Invalid phone number", "raw": None}

    if len(clean_phone) == 10:
        clean_phone = "91" + clean_phone

    base_clean = base if base.endswith("/") else base + "/"
    url = f"{base_clean}api/v1/sendSessionFile/{clean_phone}"
    params = {"caption": caption} if caption else None
    headers = {"Authorization": token}

    logger.info(f"[wati_client] POST image to {url} | file={file_name} | phone={clean_phone}")

    import io
    try:
        async with httpx.AsyncClient(timeout=WATI_TIMEOUT, verify=False) as client:
            files = {"file": (file_name, io.BytesIO(content), "image/jpeg")}
            resp = await client.post(
                url,
                params=params,
                headers=headers,
                files=files,
            )
    except httpx.TimeoutException:
        logger.error("[wati_client] Timeout sending image to WATI")
        return {"ok": False, "status": None, "message": "WATI request timed out", "raw": None}
    except Exception as exc:
        logger.exception("[wati_client] Unexpected error sending image to WATI")
        return {"ok": False, "status": None, "message": f"WATI error: {exc}", "raw": None}

    logger.info(
        f"[wati_client] WATI image response | status={resp.status_code} | "
        f"body={(resp.text[:400] if resp.text else '')}"
    )

    body = None
    try:
        body = resp.json()
    except Exception:
        body = None

    is_ok = resp.status_code == 200
    if isinstance(body, dict):
        for key in ("result", "success", "ok"):
            if key in body:
                is_ok = is_ok and bool(body.get(key))
                break

    return {
        "ok": is_ok,
        "status": resp.status_code,
        "message": "Image sent to WhatsApp" if is_ok else f"WATI status {resp.status_code}: {resp.text[:100]}",
        "raw": body,
    }


