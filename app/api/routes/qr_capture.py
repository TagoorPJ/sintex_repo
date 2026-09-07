# ==========================================================
# FILE: app/api/routes/qr.py
# ==========================================================

from __future__ import annotations

import os
import requests
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_db
from app.chatbot import chatbot_orchestrator
from app.analytics.feature_usage_tracker import record_feature_result
from app.utils.logger import get_logger
from app.utils.observability import bind_trace_context, timed_requests_request, _success_from_response
from app.schemas import QRScanRequest
logger = get_logger(__name__)

router = APIRouter(prefix="/qr", tags=["qr"])




# ==========================================================
# HELPERS
# ==========================================================
def format_indian_number(number: str) -> str:
    number = ''.join(filter(str.isdigit, str(number)))

    if len(number) == 10:
        return "91" + number

    if len(number) == 12 and number.startswith("91"):
        return number

    return number


async def send_wati_text_message(whatsapp_number: str, message: str):
    import os
    import requests
    wati_url = os.getenv("WATI_BASE_URL")
    wati_token = os.getenv("WATI_TOKEN")
    logger.info(f"[QR] sending WhatsApp message to {whatsapp_number}")
    whatsapp_number = format_indian_number(whatsapp_number)
    

    response = requests.post(
        f"{wati_url}/{whatsapp_number}",
        headers={
            "Authorization": f"Bearer {wati_token}"
        },
        params={
            "messageText": message
        },
        timeout=60
    )


    response.raise_for_status()

async def translate_message(text: str, language: str) -> str:
    if not language or language.lower() == "english":
        # If user is on English, only translate if the text is clearly NOT English.
        # We translate to English from any other language.
        prompt = f"""
You are a translator. The user's preferred language is English.
Translate the message below into clean, natural English, regardless of
its source language. Keep product codes, QR codes, numbers, and dates
exactly as they appear in the original. Return ONLY the translated text,
no preamble, no quotes.

Message:
{text}
"""
    else:
        prompt = f"""
You are a translator. The user's preferred language is {language}.
Translate the message below into clean, natural {language}, regardless
of its source language. Keep product codes, QR codes, numbers, and dates
exactly as they appear in the original. Return ONLY the translated text,
no preamble, no quotes.

Message:
{text}
"""
    result = await chatbot_orchestrator.llm.ainvoke(prompt)
    return result.content.strip()


async def _record_failed_qr_attempt(db, user, conversation, reason: str) -> None:
    """Persist a QR failure even when the callback stops before its normal reply."""
    if user is None or conversation is None:
        return
    try:
        attempt_message = await crud.save_message(
            db=db,
            conversation_id=conversation.id,
            user_id=user.id,
            sender="tool",
            message="[QR scan attempt failed]",
        )
        await record_feature_result(
            "upload.scan_qr",
            success=False,
            reason=reason,
            context={
                "user_id": user.id,
                "conversation_id": conversation.id,
                "message_id": attempt_message.id,
                "mobile_number": user.mobile_number,
                "raw_user_message": "[QR callback attempt]",
            },
        )
    except Exception:
        logger.exception("[QR] unable to record failed feature attempt")
# ==========================================================
# ENDPOINT
# ==========================================================

@router.post(
    "/callback",
    status_code=status.HTTP_200_OK
)
async def qr_callback(
    request: QRScanRequest,
    db: AsyncSession = Depends(get_db)
):
    user = None
    conversation = None
    try:
        user = await crud.get_user_by_mobile(
            db=db,
            mobile_number=request.whatsapp_number
        )

        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )

        conversation = await crud.get_or_create_conversation(
            db=db,
            user_id=user.id
        )

        bind_trace_context(
            conversation_id=conversation.id,
            user_id=user.id,
            mobile_number=user.mobile_number,
        )

        language = conversation.language or "english"

        # ----------------------------------------------
        # EXTERNAL API CALL
        # ----------------------------------------------
        base_url = os.getenv("EVOLVE_API_URL")
        token = os.getenv("EVOLVE_TOKEN")
        program = os.getenv("EVOLVE_PROGRAM")
        app_name = os.getenv("EVOLVE_APP")
        logger.info("Just about to hit evolve api")
        api_url= f"{base_url}/capture-qr"

        capture_payload: dict = {
            "user_id": request.user_id_evolve,
            "process": True,
            "qrcode": request.qrcode,
        }

        # Include dealer code only when provided by the scanner frontend
        if request.dealer_code:
            dealer_code = str(request.dealer_code).strip()

            # 🔥 REMOVE UNWANTED CHARACTERS
            dealer_code = dealer_code.strip('"').strip("'").strip()

            # Optional: keep only digits (recommended)
            dealer_code = ''.join(filter(str.isdigit, dealer_code))

            if dealer_code:
                capture_payload["retailerRtCode"] = dealer_code
                logger.info(f"[QR] cleaned retailerRtCode: {dealer_code}")
            else:
                logger.warning("[QR] dealer_code became empty after cleaning")
        logger.info(f"[QR] payload to capture-qr api: {capture_payload}")
        response = await timed_requests_request(
            "POST",
            api_url,
            api_name="evolve.capture_qr",
            endpoint="/capture-qr",
            log=logger,
            headers={
                "accept": "*/*",
                "program": program,
                "app": app_name,
                "Authorization": f"{token}",
                "Content-Type": "application/json",
            },
            json=capture_payload,
            timeout=60,
        )

        response.raise_for_status()

        data = response.json()
        logger.info(f"[QR] response from Sintex API: {data}")

        raw_message = data.get(
            "message",
            "QR scanned successfully."
        )

        # ----------------------------------------------
        # TRANSLATE
        # ----------------------------------------------
        final_message = await translate_message(
            raw_message,
            language
        )

        # ----------------------------------------------
        # SEND WATI
        # ----------------------------------------------
        await send_wati_text_message(
            whatsapp_number=user.mobile_number,
            message=final_message
        )

        # ----------------------------------------------
        # SAVE HISTORY
        # ----------------------------------------------
        completion_message = await crud.save_message(
            db=db,
            conversation_id=conversation.id,
            user_id=user.id,
            sender="assistant",
            message=final_message
        )

        qr_success = isinstance(data, dict) and _success_from_response(response, (200, 201))
        await record_feature_result(
            "upload.scan_qr",
            success=qr_success,
            reason=None if qr_success else str(data.get("message") or "QR scan failed"),
            context={
                "user_id": user.id,
                "conversation_id": conversation.id,
                "message_id": completion_message.id,
                "mobile_number": user.mobile_number,
                "raw_user_message": "[QR callback attempt]",
            },
        )

        return {
            "status": "success",
            "message": final_message,
            "mobile_number":user.mobile_number
        }

    except requests.HTTPError as e:
        logger.error(f"QR HTTP Error: {str(e)}", exc_info=True)
        await _record_failed_qr_attempt(db, user, conversation, str(e))
        raise HTTPException(
            status_code=502,
            detail="External API failed"
        )

    except Exception as e:
        logger.error(f"QR Callback Failed: {str(e)}", exc_info=True)
        await _record_failed_qr_attempt(db, user, conversation, str(e))
        raise HTTPException(
            status_code=500,
            detail="QR processing failed"
        )
