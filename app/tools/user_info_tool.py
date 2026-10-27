from __future__ import annotations

import json
import os
import re
from typing import Any, Dict

import httpx
from langchain_core.tools import tool
from dotenv import load_dotenv
from openai import AsyncAzureOpenAI
from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate as indic_transliterate

from app.utils.logger import get_logger
from app.utils.observability import timed_httpx_request
from app.utils.evolve_member_validator import (
    MemberValidationError,
    validate_member_by_mobile,
)

# ── Load environment variables ────────────────────────────────
load_dotenv()

logger = get_logger(__name__)


def format_wati_mobile_number(mobile_number: str) -> str:
    digits = "".join(filter(str.isdigit, str(mobile_number)))
    if len(digits) == 10:
        return "91" + digits
    return digits


# ───────────────────────────────────────────────────────────────
# API CALLER (ENV BASED)
# ───────────────────────────────────────────────────────────────

async def call_evolve_api(payload: Dict[str, Any]) -> Dict[str, Any]:
    BASE_URL = os.getenv("EVOLVE_API_URL")

    headers = {
        "accept": "*/*",
        "program": os.getenv("EVOLVE_PROGRAM", "1"),
        "app": os.getenv("EVOLVE_APP", "PLUMBER"),
        "Content-Type": "application/json"
    }

    api_key = os.getenv("EVOLVE_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    if not BASE_URL:
        logger.error("[EVOLVE] API URL not configured")
        return {"status": "error", "message": "API URL missing"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            url = f"{BASE_URL}/register"
            resp = await timed_httpx_request(
                client,
                "POST",
                url,
                api_name="evolve.register",
                endpoint="/register",
                log=logger,
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()

            logger.info(f"[EVOLVE] Success status={resp.status_code}")
            logger.info(f"[EVOLVE] Response body: {resp.text}")
            return resp.json()

    except httpx.HTTPStatusError as e:
        logger.error(f"[EVOLVE] HTTP error: {str(e)}")
        try:
            err_data = e.response.json()
            if isinstance(err_data, dict) and err_data.get("message"):
                return {"status": "error", "message": err_data.get("message")}
        except Exception:
            pass
        return {"status": "error", "message": str(e)}

    except Exception as e:
        logger.error(f"[EVOLVE] Unexpected error: {str(e)}")
        return {"status": "error", "message": str(e)}
async def update_member_id_in_wati(mobile_number: str, member_id: str):
    WATI_BASE_URL = os.getenv("WATI_BASE_URL")
    WATI_TOKEN = os.getenv("WATI_TOKEN")
    wati_mobile_number = format_wati_mobile_number(mobile_number)

    url = f"{WATI_BASE_URL}/updateContactAttributes/{wati_mobile_number}"

    headers = {
        "accept": "*/*",
        "Authorization": f"Bearer {WATI_TOKEN}",
        "Content-Type": "application/json-patch+json"
    }

    payload = {
        "customParams": [
            {
                "name": "memberID",
                "value": member_id
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                json=payload,
                headers=headers,
            )

            if resp.status_code == 200:
                logger.info(f"[WATI] memberID updated for {wati_mobile_number}")
            else:
                logger.error(f"[WATI] Failed: {resp.status_code} | {resp.text}")

    except Exception as e:
        logger.error(f"[WATI] Exception: {str(e)}")
def normalize_mobile_number(mobile: str) -> str:
    mobile = mobile.strip()

    # remove spaces
    mobile = mobile.replace(" ", "")

    # remove + if present
    if mobile.startswith("+"):
        mobile = mobile[1:]

    # remove country code 91 (India)
    if mobile.startswith("91") and len(mobile) > 10:
        mobile = mobile[2:]

    # remove leading 0
    if mobile.startswith("0") and len(mobile) > 10:
        mobile = mobile[1:]

    return mobile


_ITRANS_TO_LOWER = str.maketrans(
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ',
    'abcdefghijklmnopqrstuvwxyz',
)

def _has_devanagari(text: str) -> bool:
    return any('ऀ' <= c <= 'ॿ' for c in text)

def _itrans_fallback(name: str) -> str:
    """Rule-based ITRANS fallback when LLM is unavailable."""
    itrans = indic_transliterate(name, sanscript.DEVANAGARI, sanscript.ITRANS)
    plain = itrans.translate(_ITRANS_TO_LOWER)
    plain = re.sub(r"[^a-z '-]", "", plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain.title()

async def transliterate_to_english_name(name: str) -> str:
    """Convert a Devanagari (Hindi/Marathi) name to plain English using LLM.
    Falls back to rule-based ITRANS if the LLM call fails.
    Pure-ASCII names are returned unchanged."""
    if not _has_devanagari(name):
        return name

    try:
        client = AsyncAzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
        )
        response = await client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_MODEL"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a transliteration assistant. "
                        "Convert the given Indian name (Hindi/Marathi/Devanagari script) "
                        "to its standard English spelling. "
                        "Return ONLY the transliterated name — no explanation, no punctuation, nothing else."
                    ),
                },
                {"role": "user", "content": name},
            ],
            temperature=0,
            max_tokens=50,
        )
        result = response.choices[0].message.content.strip()
        # Sanity check: result must be non-empty and ASCII-only
        if result and result.isascii():
            logger.info(f"[TRANSLITERATE] LLM: {name!r} → {result!r}")
            return result
        logger.warning(f"[TRANSLITERATE] LLM returned non-ASCII, falling back: {result!r}")
    except Exception as e:
        logger.warning(f"[TRANSLITERATE] LLM failed, falling back to ITRANS: {e}")

    fallback = _itrans_fallback(name)
    logger.info(f"[TRANSLITERATE] ITRANS fallback: {name!r} → {fallback!r}")
    return fallback


# ───────────────────────────────────────────────────────────────
# TOOL
# ───────────────────────────────────────────────────────────────

@tool("submit_user_registration")
async def submit_user_registration(payload: str) -> str:
    """
    Submits plumber registration data to the backend API and creates a new member profile. On success, it returns a unique User ID.

    Required fields (mandatory):
    - name
    - mobile_number
    - pincode

    The tool must not be called unless all required fields are present.

    Optional fields (include only if provided by the user):
    - number_of_permanent_employees
    - number_of_concurrent_sites
    - annual_water_storage_tank_volume_in_litres
    - major_brands_you_use_in_water_tank
    - annual_pipes_and_fittings_value_in_lakhs
    - major_brands_you_use_in_pipes

    Do not send null, empty, or missing values.

    Callback behavior:
    - If callback = true:
    Call the tool immediately after collecting mandatory fields. Do not wait for optional data.
    - If callback = false:
    You may collect optional business details, but the tool can still be called with only mandatory fields.

    Input format:
    Payload must be a valid JSON string containing:
    - name (string)
    - mobile_number (string)
    - pincode (string or number)
    - callback (boolean, optional)
    - optional fields (if available)

    Response behavior:
    - On success (callback = false):
    Returns JSON: {"status": "success", "user_id": "...", "message": "..."}

    - On success (callback = true):
    Returns JSON: {"status": "success", "user_id": "...", "message": "..."}

    - On pincode not found:
    Returns JSON: {"status": "pincode_error", "message": "pincode_not_found"}
    → When you receive this, tell the user the pincode they entered is not supported
      or not recognized, and ask them to enter a different valid pincode.
      Do NOT end the registration. Wait for the new pincode and call this tool again.

    - On other failure:
    Returns JSON: {"status": "error", "message": "<specific error reason from API>"}
    → When you receive this, clearly inform the user about the exact reason given in the message.

    Important rules:
    - Never call the tool without mandatory fields
    - Never assume or fabricate data
    - Always send values in English
    - Always send clean and valid JSON
    - Call immediately once required data is available
    """

    logger.info("[REGISTRATION TOOL] Start")
    logger.info(f"[REGISTRATION TOOL] Raw payload: {payload}")

    # ── 1. Parse payload ────────────────────────────────────────
    try:
        data: Dict[str, Any] = json.loads(payload)
    except Exception as e:
        logger.error(f"[REGISTRATION TOOL] Invalid JSON: {str(e)}")
        return "Invalid data format. Please try again."

    logger.info(f"[REGISTRATION TOOL] Keys received: {list(data.keys())}")

    callback = bool(data.get("callback", False))

    # ── 2. REQUIRED FIELD VALIDATION ────────────────────────────
    required_fields = ["name", "mobile_number", "pincode"]

    missing_fields = [
        f for f in required_fields
        if f not in data or data[f] in [None, ""]
    ]

    if missing_fields:
        return "Please provide name, mobile number, and pincode."

    raw_name = str(data.get("name")).strip()
    name = await transliterate_to_english_name(raw_name)
    if name != raw_name:
        logger.info(f"[REGISTRATION TOOL] Name transliterated: {raw_name!r} → {name!r}")
    raw_mobile = str(data.get("mobile_number"))
    mobile = normalize_mobile_number(raw_mobile)
    pincode = str(data.get("pincode")).strip()

    # ── 3. SCHEMA VALIDATION ────────────────────────────────────

    # Name validation
    if len(name) < 2:
        return "Please enter a valid full name."

    # Mobile validation (10 digit numeric)
    if not (mobile.isdigit() and len(mobile) == 10):
        return "Please enter a valid 10-digit mobile number."

    # Pincode validation (6 digit numeric)
    if not (pincode.isdigit() and len(pincode) == 6):
        return "Please enter a valid 6-digit pincode."

    # ── 4. OPTIONAL FIELD VALIDATION ────────────────────────────
    def validate_number(field_name: str, value: Any):
        try:
            return int(value)
        except:
            raise ValueError(f"Invalid value for {field_name}. Please enter a number.")

    optional_numeric_fields = [
        "number_of_permanent_employees",
        "number_of_concurrent_sites",
        "annual_water_storage_tank_volume_in_litres",
        "annual_pipes_and_fittings_value_in_lakhs",
    ]

    validated_optional_data = {}

    for field in optional_numeric_fields:
        value = data.get(field)
        if value not in [None, ""]:
            try:
                validated_optional_data[field] = validate_number(field, value)
            except ValueError as e:
                return str(e)

    # Free text fields (just clean)
    text_fields = [
        "major_brands_you_use_in_water_tank",
        "major_brands_you_use_in_pipes",
    ]

    for field in text_fields:
        value = data.get(field)
        if value not in [None, ""]:
            validated_optional_data[field] = str(value).strip()

    # ── 5. BUILD API PAYLOAD ────────────────────────────────────
    api_payload = {
        "name": name,
        "mobile_number": mobile,
        "pincode": pincode,
    }

    api_payload.update(validated_optional_data)

    logger.info(f"[REGISTRATION TOOL] API payload → {api_payload}")

    # ── 6. CALL API ─────────────────────────────────────────────
    api_result = await call_evolve_api(api_payload)
    is_new_registration = True

    if api_result.get("status") == "error":
        api_message = (api_result.get("message") or "").strip()
        last_validation_message = None

        # Evolve may know this mobile as an existing member while our local
        # database is missing its member ID. Recover that ID through the
        # validation endpoint instead of leaving the user stuck in registration.
        if "already registered" in api_message.lower():
            is_new_registration = False
            logger.info(
                "[REGISTRATION TOOL] Existing Evolve registration detected; "
                "recovering member ID through validation | mobile=%s",
                mobile,
            )
            raw_mobile_digits = "".join(c for c in raw_mobile if c.isdigit())
            validation_candidates = []
            for candidate in (raw_mobile_digits, mobile, f"91{mobile}"):
                if candidate and candidate not in validation_candidates:
                    validation_candidates.append(candidate)

            validation = None
            for candidate in validation_candidates:
                try:
                    candidate_result = await validate_member_by_mobile(candidate)
                    if candidate_result.message:
                        last_validation_message = candidate_result.message
                except MemberValidationError:
                    logger.warning(
                        "[REGISTRATION TOOL] Existing-member validation attempt "
                        "failed | mobile=%s",
                        candidate,
                    )
                    continue
                if candidate_result.is_valid and candidate_result.member_id:
                    validation = candidate_result
                    break

            if validation is not None:
                if validation.is_valid and validation.member_id:
                    api_result = {
                        "status": "success",
                        "member_id": validation.member_id,
                        "message": "Existing registration recovered.",
                    }
                    logger.info(
                        "[REGISTRATION TOOL] Existing member ID recovered | "
                        "mobile=%s | member_id=%s",
                        mobile,
                        validation.member_id,
                    )
            else:
                logger.error(
                    "[REGISTRATION TOOL] Evolve reported already registered "
                    "but validation found no member ID | mobile=%s | validation_message=%s",
                    mobile,
                    last_validation_message,
                )

        if api_result.get("status") == "success":
            pass
        else:
            error_reason = last_validation_message or api_result.get("message") or "Registration failed. Please try again later."
            if "pincode" in error_reason.lower() or "pincode" in api_message.lower():
                logger.error(f"[REGISTRATION TOOL] API failed (pincode): {api_result} | reason: {error_reason}")
                return json.dumps({
                    "status": "pincode_error",
                    "message": "pincode_not_found",
                })
            else:
                logger.error(f"[REGISTRATION TOOL] API failed: {api_result} | reason: {error_reason}")
                return json.dumps({
                    "status": "error",
                    "message": error_reason,
                })

    logger.info("[REGISTRATION TOOL] Success")

    user_id_evolve_generated = api_result.get("member_id")
    # ✅ CALL WATI AFTER REGISTRATION SUCCESS
    if user_id_evolve_generated:
        try:
            await update_member_id_in_wati(
                mobile_number=raw_mobile,
                member_id=user_id_evolve_generated
            )
        except Exception as e:
            logger.error(f"[WATI] Failed to update memberID: {str(e)}")

    # ── 7. RESPONSE ─────────────────────────────────────────────
    if callback:
        return json.dumps({
            "status": "success",
            "user_id": user_id_evolve_generated,
            "name": name,
            "registered_via_chatbot": is_new_registration,
            "message": (
                f"Registration successful!\n"
                f"Your User ID: {user_id_evolve_generated}\n"
                f"Our team will call you shortly."
            ),
        })

    return json.dumps({
        "status": "success",
        "user_id": user_id_evolve_generated,
        "name": name,
        "registered_via_chatbot": is_new_registration,
        "message": (
            f"Registration successful!\n"
            f"Your User ID: {user_id_evolve_generated}\n"
            f"Our team will contact you shortly."
        ),
    })
