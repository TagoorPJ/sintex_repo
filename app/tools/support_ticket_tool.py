from __future__ import annotations

import os
import json
import httpx
import smtplib
import mimetypes
from email.message import EmailMessage
from pathlib import Path
from dotenv import load_dotenv
from langchain.tools import tool

from app.utils.logger import get_logger
from app.utils.observability import timed_httpx_request

load_dotenv()
logger = get_logger(__name__)

BASE_URL = os.getenv("EVOLVE_API_URL", "").rstrip("/")
PROGRAM = os.getenv("EVOLVE_PROGRAM")
APP_NAME = os.getenv("EVOLVE_APP")
AUTH_TOKEN = os.getenv("EVOLVE_TOKEN")
# WATI_BASE_URL points to the sendSessionMessage endpoint
# (e.g. https://live-mt-server.wati.io/304878/api/v1/sendSessionMessage).
# For media download we need the api/v1 base, so strip the last path segment.
_wati_raw = os.getenv("WATI_BASE_URL", "").rstrip("/")
WATI_MEDIA_BASE_URL = _wati_raw.rsplit("/", 1)[0] if "/" in _wati_raw else _wati_raw
WATI_TOKEN = os.getenv("WATI_TOKEN", "")
REQUEST_TIMEOUT = float(os.getenv("EVOLVE_TIMEOUT", "15"))

# ── Email config ─────────────────────────────────────────────────
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.office365.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_RECIPIENTS = [e.strip() for e in os.getenv("EMAIL_RECIPIENTS", "").split(",") if e.strip()]

# ── Image storage ─────────────────────────────────────────────────
IMAGE_SAVE_DIR = Path(os.getenv("IMAGE_SAVE_DIR", "/tmp/sintex_images"))
IMAGE_PUBLIC_BASE = os.getenv("IMAGE_PUBLIC_BASE", "").rstrip("/")

HEADERS = {
    "accept": "*/*",
    "program": PROGRAM,
    "app": APP_NAME,
    "Content-Type": "application/json",
    "Authorization": AUTH_TOKEN,
}

ISSUE_TYPES = {
    "1": "Product Complaint",
    "2": "Loyalty Issue",
    "3": "Dealer Problem",
    "4": "Service Request",
}


def _json_response(status: str, message: str, data: dict = None) -> str:
    payload = {"status": status, "message": message}
    if data:
        payload.update(data)
    return json.dumps(payload, ensure_ascii=False)


async def _download_and_save_wati_media(file_name: str) -> tuple[str | None, str | None]:
    """
    Downloads image from WATI, saves it to IMAGE_SAVE_DIR, and returns
    (saved_file_path, public_url). Returns (None, None) on failure.
    """
    if not file_name or not WATI_MEDIA_BASE_URL:
        return None, None

    wati_url = f"{WATI_MEDIA_BASE_URL}/getMedia?fileName={file_name}"
    headers = {"Authorization": f"Bearer {WATI_TOKEN}"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                wati_url,
                headers=headers,
            )

        if resp.status_code != 200:
            logger.error(f"[SUPPORT TICKET] WATI media fetch failed: {resp.status_code}")
            return None, None

        # Determine file extension from content-type or original filename
        content_type = resp.headers.get("content-type", "")
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ""
        if not ext or ext == ".jpe":
            ext = ".jpg"

        # Sanitise the WATI fileName for use as the saved filename
        safe_name = Path(file_name).name
        if not safe_name.lower().endswith(ext):
            save_name = f"{safe_name}{ext}"
        else:
            save_name = safe_name

        save_path = IMAGE_SAVE_DIR / save_name

        IMAGE_SAVE_DIR.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(resp.content)

        public_url = f"{IMAGE_PUBLIC_BASE}/{save_name}"
        logger.info(f"[SUPPORT TICKET] Image saved: {save_path} | URL: {public_url}")
        return str(save_path), public_url

    except Exception:
        logger.exception("[SUPPORT TICKET] Failed to download/save WATI media")
        return None, None


def _send_ticket_email(
    ticket_id: str,
    issue_type: str,
    description: str,
    user_id: int,
    image_path: str | None,
    image_url: str | None,
) -> None:
    """Send support ticket details via SMTP. Runs synchronously — call in a thread if needed."""
    msg = EmailMessage()
    msg["Subject"] = f"Sintex Support Ticket #{ticket_id} — {issue_type}"
    msg["From"] = SMTP_USER
    msg["To"] = ", ".join(EMAIL_RECIPIENTS)

    image_note_text = "Image     : See attached." if image_path else "Image     : No image attached."

    # Plain-text fallback
    msg.set_content(
        f"Sintex Support Ticket #{ticket_id}\n"
        f"{'─' * 35}\n"
        f"Ticket ID  : {ticket_id}\n"
        f"Issue Type : {issue_type}\n"
        f"User ID    : {user_id}\n"
        f"{'─' * 35}\n"
        f"Description:\n{description}\n"
        f"{'─' * 35}\n"
        f"{image_note_text}\n"
    )

    # HTML version — shown by default in modern email clients
    msg.add_alternative(
        f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:30px 0;">
    <tr><td align="center">
      <table width="580" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:8px;overflow:hidden;
                    box-shadow:0 2px 8px rgba(0,0,0,0.08);">

        <!-- Header -->
        <tr>
          <td style="background:#1a6b3c;padding:20px 30px;">
            <h2 style="margin:0;color:#ffffff;font-size:18px;">
              🎫 Sintex Support Ticket #{ticket_id}
            </h2>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:28px 30px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="padding:6px 0;color:#555;font-size:13px;width:120px;">Ticket ID</td>
                <td style="padding:6px 0;font-size:13px;font-weight:bold;">#{ticket_id}</td>
              </tr>
              <tr style="background:#f9f9f9;">
                <td style="padding:6px 0;color:#555;font-size:13px;">Issue Type</td>
                <td style="padding:6px 0;font-size:13px;">{issue_type}</td>
              </tr>
              <tr>
                <td style="padding:6px 0;color:#555;font-size:13px;">User ID</td>
                <td style="padding:6px 0;font-size:13px;">{user_id}</td>
              </tr>
            </table>

            <!-- Description -->
            <div style="margin-top:20px;">
              <p style="margin:0 0 8px;font-size:13px;color:#555;font-weight:bold;">
                Description
              </p>
              <div style="background:#f4f4f4;border-left:4px solid #1a6b3c;
                          padding:12px 16px;border-radius:4px;font-size:14px;
                          color:#333;line-height:1.6;">
                {description}
              </div>
            </div>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f4f4f4;padding:14px 30px;text-align:center;">
            <p style="margin:0;font-size:11px;color:#aaa;">
              This is an automated notification from the Sintex Chatbot.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>""",
        subtype="html",
    )

    # Attach the image file if it was saved successfully
    if image_path:
        try:
            img_bytes = Path(image_path).read_bytes()
            mime_type, _ = mimetypes.guess_type(image_path)
            maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
            msg.add_attachment(
                img_bytes,
                maintype=maintype,
                subtype=subtype,
                filename=Path(image_path).name,
            )
        except Exception:
            logger.warning("[SUPPORT TICKET] Could not attach image to email")

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.send_message(msg)
        logger.info(f"[SUPPORT TICKET] Email sent for ticket {ticket_id}")
    except Exception:
        logger.exception(f"[SUPPORT TICKET] Email send failed for ticket {ticket_id}")


@tool("support_ticket_tool")
async def support_ticket_tool(payload: str) -> str:
    """
    Tool Name: support_ticket_tool

    Purpose:
    Raises a support ticket for the user. Collects issue type, description, and an optional image.

    Issue Types:
    1. Product Complaint
    2. Loyalty Issue
    3. Dealer Problem
    4. Service Request

    Flow:
    STEP 1 — Show the issue type submenu (do NOT call this tool yet):
        "Please select the type of issue:
        1. Product Complaint
        2. Loyalty Issue
        3. Dealer Problem
        4. Service Request"

    STEP 2 — Wait for user to select a number (1-4). Map to issue type name.

    STEP 3 — Ask user to describe the issue in detail.

    STEP 4 — Ask if they have an image to attach (optional). If user says no or skips, proceed without image.

    STEP 5 — Call this tool with the collected data.

    Parameters (JSON string):
    - user_id_evolve (Required): from COLLECTED_DATA, never ask user
    - issue_type (Required): one of "Product Complaint", "Loyalty Issue", "Dealer Problem", "Service Request"
    - description (Required): user's issue description
    - attachment (Optional): WATI fileName string from the incoming WhatsApp message (if user sent an image)

    Rules:
    - Never call this tool before collecting issue_type and description
    - user_id_evolve comes from COLLECTED_DATA only — never ask the user
    - attachment is the raw WATI fileName — the tool handles downloading it
    - If no attachment, omit the field or pass null

    Success Response:
    {
        "status": "success",
        "message": "Your support ticket has been raised successfully. Ticket ID: <id>",
        "ticket_id": "<id>"
    }

    Error Response:
    {
        "status": "error",
        "message": "Reason for failure"
    }
    """

    logger.info(f"[support_ticket_tool] Called | raw payload: {payload}")

    # ── Parse payload ────────────────────────────────────────────
    try:
        data: dict = json.loads(payload)
    except Exception as e:
        logger.error(f"[support_ticket_tool] Invalid JSON: {e}")
        return _json_response("error", "Invalid data format. Please try again.")

    user_id_evolve = data.get("user_id_evolve")
    issue_type = (data.get("issue_type") or "").strip()
    description = (data.get("description") or "").strip()
    # Sanitize WATI no-attachment sentinels ("NA", "null", "none", etc.)
    _raw_attachment = (data.get("attachment") or "").strip()
    attachment = None if _raw_attachment.lower() in {"", "na", "null", "none", "undefined", "false", "nil"} else _raw_attachment

    # ── Validate required fields ─────────────────────────────────
    if not user_id_evolve:
        return _json_response("error", "User ID is required.")

    try:
        user_id_int = int(user_id_evolve)
    except (ValueError, TypeError):
        return _json_response("error", "Invalid user ID.")

    valid_issue_types = set(ISSUE_TYPES.values())
    if issue_type not in valid_issue_types:
        return _json_response(
            "error",
            f"Invalid issue type. Must be one of: {', '.join(valid_issue_types)}"
        )

    if not description:
        return _json_response("error", "Issue description is required.")

    # ── Download and save attachment if provided ─────────────────
    saved_image_path = None
    image_public_url = None
    if attachment:
        saved_image_path, image_public_url = await _download_and_save_wati_media(attachment)
        logger.info(
            f"[support_ticket_tool] Attachment saved: {saved_image_path} | URL: {image_public_url}"
        )

    # ── Build API payload ────────────────────────────────────────
    api_payload = {
        "user_id": user_id_int,
        "type": issue_type,
        "description": description,
        "ticket_img": image_public_url or "",
    }

    logger.info(f"[support_ticket_tool] API payload: {api_payload}")

    # ── Call API ─────────────────────────────────────────────────
    url = f"{BASE_URL}/support-ticket"

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await timed_httpx_request(
                client,
                "POST",
                url,
                api_name="evolve.support_ticket",
                endpoint="/support-ticket",
                log=logger,
                json=api_payload,
                headers=HEADERS,
            )

        logger.info(f"[support_ticket_tool] API Status={response.status_code}")
        logger.info(f"[support_ticket_tool] API Response={response.text}")

        if response.status_code not in (200, 201):
            logger.error(
                f"[support_ticket_tool] Non-200 response: {response.status_code} | {response.text}"
            )
            return _json_response(
                "error", "Unable to raise support ticket right now. Please try again later."
            )

        result = response.json()

        if result.get("status") == "error":
            return _json_response(
                "error",
                result.get("message", "Failed to raise support ticket.")
            )

        ticket_id = result.get("ticket_id") or result.get("id") or result.get("ticketId")

        # ── Send email notification ──────────────────────────────
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                _send_ticket_email,
                str(ticket_id),
                issue_type,
                description,
                user_id_int,
                saved_image_path,
                image_public_url,
            )
        except Exception:
            logger.exception("[support_ticket_tool] Email notification failed (non-fatal)")

        return _json_response(
            "success",
            f"Your support ticket has been raised successfully.\nTicket ID: {ticket_id}",
            {"ticket_id": ticket_id},
        )

    except httpx.TimeoutException:
        logger.error("[support_ticket_tool] Request timed out")
        return _json_response(
            "error", "Request timed out. Please try again."
        )

    except Exception:
        logger.exception("[support_ticket_tool] Unexpected error")
        return _json_response(
            "error", "Something went wrong while raising the support ticket."
        )
