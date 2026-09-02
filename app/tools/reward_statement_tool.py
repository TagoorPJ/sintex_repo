# app/tools/reward_statement_tool.py

from __future__ import annotations

import os
import json
from datetime import datetime, timedelta
from typing import Optional

import httpx
from dotenv import load_dotenv
from langchain.tools import tool

from app.utils.logger import get_logger
from app.utils.observability import timed_httpx_request
from app.utils.pdf_utils import create_reward_statement_pdf
from app.utils.wati_client import send_session_document

load_dotenv()
logger = get_logger(__name__)

# ---------------------------------------------------------
# ENV CONFIG
# ---------------------------------------------------------
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


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------
def _json_response(status: str, message: str, data: dict = None) -> str:
    payload = {
        "status": status,
        "message": message,
    }
    if data:
        payload.update(data)
    return json.dumps(payload, ensure_ascii=False)


def _safe_int(value):
    try:
        return int(value)
    except Exception:
        return None


def _is_valid_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except Exception:
        return False


# ---------------------------------------------------------
# LANGUAGE-AWARE USER MESSAGES
# ---------------------------------------------------------
# The tool's `message` field is what the user actually sees, because
# the chatbot returns it directly via DIRECT_TOOL_RESPONSE_TOOLS. Hard-
# coding these per language stops the LLM from paraphrasing or dropping
# the "PDF on its way" acknowledgement.

_MSG_PDF_SENT = {
    "english":  "📄 Your reward statement PDF has been sent to your WhatsApp.\n\n"
                "Period: {f} to {t}\nTotal Transactions: {n}\nTotal Points: {p:.0f}",
    "hindi":    "📄 आपका रिवॉर्ड स्टेटमेंट PDF आपके WhatsApp पर भेज दिया गया है।\n\n"
                "अवधि: {f} से {t}\nकुल लेनदेन: {n}\nकुल पॉइंट्स: {p:.0f}",
    "marathi":  "📄 तुमचा रिवॉर्ड स्टेटमेंट PDF तुमच्या WhatsApp वर पाठवला आहे.\n\n"
                "कालावधी: {f} ते {t}\nएकूण व्यवहार: {n}\nएकूण पॉइंट्स: {p:.0f}",
    "hinglish": "📄 Aapka reward statement PDF aapke WhatsApp par bhej diya gaya hai.\n\n"
                "Period: {f} se {t}\nTotal Transactions: {n}\nTotal Points: {p:.0f}",
}

_MSG_NO_TXN = {
    "english":  "No reward transactions found from {f} to {t}.",
    "hindi":    "{f} से {t} तक कोई रिवॉर्ड लेनदेन नहीं मिला।",
    "marathi":  "{f} ते {t} पर्यंत कोणतेही रिवॉर्ड व्यवहार आढळले नाहीत.",
    "hinglish": "{f} se {t} tak koi reward transaction nahi mila.",
}

_MSG_PDF_FAILED = {
    "english":  "We fetched your reward statement but couldn't send the PDF to "
                "WhatsApp right now. Please try again in a few minutes.",
    "hindi":    "हमने आपका रिवॉर्ड स्टेटमेंट प्राप्त कर लिया है, लेकिन अभी PDF "
                "WhatsApp पर नहीं भेज पाए। कृपया कुछ देर बाद पुनः प्रयास करें।",
    "marathi":  "आम्ही तुमचा रिवॉर्ड स्टेटमेंट मिळवला आहे, पण आत्ता PDF "
                "WhatsApp वर पाठवू शकलो नाही. कृपया काही वेळाने पुन्हा प्रयत्न करा.",
    "hinglish": "Humne aapka reward statement le liya hai, lekin abhi PDF "
                "WhatsApp par nahi bhej paye. Thodi der baad try karein.",
}


def _lang_msg(template_map: dict, language: Optional[str], **kwargs) -> str:
    lang = (language or "english").strip().lower()
    if lang not in template_map:
        lang = "english"
    return template_map[lang].format(**kwargs)


# ---------------------------------------------------------
# TOOL
# ---------------------------------------------------------
@tool("reward_statement_tool")
async def reward_statement_tool(
    user_id_evolve: str,
    mobile_number: str,
    language: str = "english",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> str:
    """
    Tool Name: reward_statement_tool

    Purpose:
    Fetch the user's reward statement / reward earning transactions for a
    selected date range, render them into a PDF, and deliver the PDF to
    the user's WhatsApp via WATI's sendSessionFile endpoint.

    The tool returns a short text acknowledgement that is shown to the
    user directly (via DIRECT_TOOL_RESPONSE_TOOLS in the chatbot). The
    actual reward data goes to the user as a PDF attachment on WhatsApp,
    not as chat text.

    Use this tool whenever the user asks about:
    - reward statement
    - monthly rewards
    - rewards earned this month
    - points earned report
    - reward transactions
    - reward history by date
    - rewards between two dates
    - statement of earned points

    Parameters Accepted:

    1. user_id_evolve (REQUIRED, string)
       - Comes from PREFILLED_DATA.
       - Never ask the user for this.

    2. mobile_number (REQUIRED, string)
       - Comes from PREFILLED_DATA (whatsapp_number).
       - Used to send the PDF over WATI to the right person.

    3. language (OPTIONAL, string)
       - One of: "english", "hindi", "marathi", "hinglish".
       - Comes from PREFILLED_DATA. Defaults to "english".
       - Controls the wording of the chat acknowledgement only — the
         PDF body itself is in English (column headers, totals).

    4. from_date (OPTIONAL, string, YYYY-MM-DD)
    5. to_date   (OPTIONAL, string, YYYY-MM-DD)
       - Defaults when both are omitted: from_date = today - 30 days,
                                         to_date   = today
         (i.e. the past 30-day window, inclusive of today).

    Mandatory Execution Rules:
    - Always call this tool when the user asks for reward statement.
    - user_id_evolve and mobile_number are mandatory.
    - Never invent / hardcode / ask for user_id_evolve or mobile_number.
    - Validate date format before calling.

    Important Notes:
    - This tool is read-only against the rewards system.
    - It writes a PDF to disk and uploads it to WATI.
    - WATI's sendSessionFile only works inside an open 24-hour session
      with the user — that's typical for WhatsApp business chat.
    """

    logger.info(
        f"[reward_statement_tool] Called | user_id={user_id_evolve} | "
        f"mobile_number={mobile_number} | language={language} | "
        f"from_date={from_date} | to_date={to_date}"
    )

    # ---------------------------------------------------------
    # USER VALIDATION
    # ---------------------------------------------------------
    user_id = _safe_int(user_id_evolve)
    if not user_id:
        return _json_response("error", "Valid user ID is required.")

    phone = "".join(c for c in str(mobile_number or "") if c.isdigit())
    if not phone:
        return _json_response("error", "Valid mobile number is required.")

    # ---------------------------------------------------------
    # DATE DEFAULTING
    # ---------------------------------------------------------
    # If the user did NOT specify a date range, return the last 30 days:
    #   to_date   = today
    #   from_date = today - 30 days   (inclusive of today, so 30-day window)
    today = datetime.today().date()

    if not from_date or not str(from_date).strip():
        from_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    if not to_date or not str(to_date).strip():
        to_date = today.strftime("%Y-%m-%d")

    # ---------------------------------------------------------
    # DATE VALIDATION
    # ---------------------------------------------------------
    if not _is_valid_date(from_date):
        return _json_response("error", "Invalid from_date format. Use YYYY-MM-DD.")
    if not _is_valid_date(to_date):
        return _json_response("error", "Invalid to_date format. Use YYYY-MM-DD.")

    from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
    to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
    if from_dt > to_dt:
        return _json_response("error", "from_date cannot be greater than to_date.")

    # ---------------------------------------------------------
    # API CALL — fetch the statement
    # ---------------------------------------------------------
    url = f"{BASE_URL}/reward-statement"
    payload = {
        "user_id": user_id,
        "from_date": from_date,
        "to_date": to_date,
    }

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await timed_httpx_request(
                client,
                "POST",
                url,
                api_name="evolve.reward_statement",
                endpoint="/reward-statement",
                log=logger,
                json=payload,
                headers=HEADERS,
            )

        logger.info(f"[reward_statement_tool] API Status={response.status_code}")

        if response.status_code != 200:
            return _json_response("error", "Unable to fetch reward statement right now.")

        result = response.json()

        if result.get("status") != "success":
            return _json_response("error", "Reward statement not available.")

        statement = result.get("statement", []) or []

        # ---------------------------------------------------------
        # NO TRANSACTIONS — short-circuit, no PDF needed
        # ---------------------------------------------------------
        if not statement:
            return _json_response(
                "success",
                _lang_msg(_MSG_NO_TXN, language, f=from_date, t=to_date),
                {"statement": []},
            )

        # ---------------------------------------------------------
        # COMPUTE TOTALS
        # ---------------------------------------------------------
        total_points = 0.0
        for row in statement:
            try:
                total_points += float(row.get("points_earned", 0))
            except (TypeError, ValueError):
                pass
        total_transactions = len(statement)

        # ---------------------------------------------------------
        # GENERATE PDF
        # ---------------------------------------------------------
        try:
            file_name, file_path = create_reward_statement_pdf(
                customer_phone=phone,
                user_id_evolve=str(user_id_evolve),
                from_date=from_date,
                to_date=to_date,
                statement=statement,
                total_transactions=total_transactions,
                total_points=total_points,
            )
        except Exception:
            logger.exception("[reward_statement_tool] PDF generation failed")
            return _json_response(
                "error",
                _lang_msg(_MSG_PDF_FAILED, language),
                {
                    "statement": statement,
                    "total_transactions": total_transactions,
                    "total_points": total_points,
                },
            )

        # ---------------------------------------------------------
        # SEND PDF VIA WATI
        # ---------------------------------------------------------
        caption = f"Reward Statement {from_date} to {to_date}"
        wati_result = await send_session_document(
            file_path=file_path,
            file_name=file_name,
            phone=phone,
            caption=caption,
        )

        if not wati_result.get("ok"):
            logger.error(
                f"[reward_statement_tool] WATI send failed | "
                f"status={wati_result.get('status')} | "
                f"message={wati_result.get('message')}"
            )
            return _json_response(
                "error",
                _lang_msg(_MSG_PDF_FAILED, language),
                {
                    "statement": statement,
                    "total_transactions": total_transactions,
                    "total_points": total_points,
                    "wati": wati_result,
                },
            )

        # ---------------------------------------------------------
        # SUCCESS — short user-facing acknowledgement
        # ---------------------------------------------------------
        message = _lang_msg(
            _MSG_PDF_SENT,
            language,
            f=from_date,
            t=to_date,
            n=total_transactions,
            p=total_points,
        )
        return _json_response(
            "success",
            message,
            {
                "statement": statement,
                "total_transactions": total_transactions,
                "total_points": total_points,
                "pdf_file_name": file_name,
                "pdf_file_path": file_path,
                "delivered_to": phone,
            },
        )

    except httpx.TimeoutException:
        logger.error("[reward_statement_tool] Timeout")
        return _json_response("error", "Request timed out while fetching reward statement.")

    except Exception:
        logger.exception("[reward_statement_tool] Unexpected Error")
        return _json_response("error", "Something went wrong while fetching reward statement.")
