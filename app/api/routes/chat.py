from __future__ import annotations

import os
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import json
from app import crud
from app.chatbot import chatbot_orchestrator
from app.database import get_db
from app.schemas import ChatRequest, ChatResponse
from app.utils.logger import get_logger
from app.utils.observability import bind_trace_context
from app.models import ConversationStage
from datetime import datetime, timedelta, timezone
from app.utils.intent_detector import detect_intent_and_language_change_llm, classify_plumber_reply, classify_correction_intent
from langchain_core.messages import HumanMessage, AIMessage
from fastapi import Request
from app.utils.dealer_flow_stage_helper import update_dealer_flow_stage, reset_dealer_flow_stage  # ← ADD THIS
from app.upload_flow import handler as upload_flow_handler
from app.upload_flow.intent import classify_upload_intent
from app.utils.evolve_member_validator import (
    MemberValidationError,
    validate_member_by_mobile,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


def _log_user_msg(conv_id: int, message: str) -> None:
    logger.info(
        f"\n{'─'*60}\n"
        f"  📨 USER  │ conv_id={conv_id}\n"
        f"  {message}\n"
        f"{'─'*60}"
    )


def _log_bot_msg(conv_id: int, source: str, message: str) -> None:
    logger.info(
        f"\n{'─'*60}\n"
        f"  🤖 BOT   │ conv_id={conv_id} │ [{source}]\n"
        f"  {message}\n"
        f"{'─'*60}"
    )


def _resolve_scanner_base_url(http_request: Request) -> str:
    """
    Resolve the externally-visible base URL for the QR scanner page.

    Priority:
      1. SCANNER_BASE_URL env var (preferred for production — bypasses
         any reverse-proxy header confusion).
      2. http_request.base_url, which is whatever the FastAPI app sees.
         On a single-process dev box this is the right URL. Behind a
         proxy it can be wrong unless uvicorn was started with
         --proxy-headers and a trusted X-Forwarded-* header set.

    The returned string never has a trailing slash, so callers can
    safely append "/scanner?...".
    """
    override = (os.getenv("SCANNER_BASE_URL") or "").strip()
    if override:
        return override.rstrip("/")
    return str(http_request.base_url).rstrip("/")


def is_valid_user_id_evolve(user_id: str | None) -> bool:
    if not user_id:
        return False

    user_id = str(user_id).strip()

    if user_id.lower() in ["", "null", "none", "undefined"]:
        return False

    return True

# WATI no-attachment sentinels — any of these mean "no file was sent".
_WATI_EMPTY_ATTACHMENT = {"", "na", "null", "none", "undefined", "false", "nil"}

def _sanitize_attachment(value: str | None) -> str | None:
    """Return None if value is a WATI no-attachment sentinel, else the raw value."""
    if not value:
        return None
    if value.strip().lower() in _WATI_EMPTY_ATTACHMENT:
        return None
    return value.strip()

# ── PROFESSION CHECK HELPERS ─────────────────────────────────────────────────

_PROFESSION_ASK: dict[str, str] = {
    "english":  "Are you a plumber / plumbing contractor?\n\n1. Yes\n2. No",
    "hindi":    "क्या आप प्लंबर / प्लंबिंग कॉन्ट्रैक्टर हैं?\n\n1. हाँ\n2. नहीं",
    "marathi":  "तुम्ही प्लंबर / प्लंबिंग कॉन्ट्रॅक्टर आहात का?\n\n1. होय\n2. नाही",
    "hinglish": "Kya aap plumber / plumbing contractor hain?\n\n1. Haan\n2. Nahi",
}

_PROFESSION_REASK: dict[str, str] = {
    "english":  "Please reply *1* for Yes or *2* for No.\n\nAre you a plumber / plumbing contractor?",
    "hindi":    "कृपया *1* (हाँ) या *2* (नहीं) भेजें।\n\nक्या आप प्लंबर / प्लंबिंग कॉन्ट्रैक्टर हैं?",
    "marathi":  "कृपया *1* (होय) किंवा *2* (नाही) पाठवा.\n\nतुम्ही प्लंबर / प्लंबिंग कॉन्ट्रॅक्टर आहात का?",
    "hinglish": "Kripaya *1* (Haan) ya *2* (Nahi) bhejo.\n\nKya aap plumber / plumbing contractor hain?",
}

_NOT_PLUMBER_BLOCKED: dict[str, str] = {
    "english": (
        "Please note that this feature is reserved for "
        "Sintex Distributors/Plumber/Plumbing Contractor only.\n\n"
        "Unfortunately, we are unable to proceed with you further.\n\n"
        "Thank you for stopping by!\nHave a great day! 😇\n\n"
        "_If you selected incorrectly, reply *I am a plumber / plumbing contractor* to continue._"
    ),
    "hindi": (
        "कृपया ध्यान दें कि यह सुविधा केवल सिन्टेक्स डिस्ट्रिब्यूटर्स / प्लंबर / प्लंबिंग कॉन्ट्रैक्टर के लिए है।\n\n"
        "दुर्भाग्यवश, हम आगे आपकी मदद करने में असमर्थ हैं।\n\n"
        "यहाँ आने के लिए धन्यवाद!\nआपका दिन शुभ हो! 😇\n\n"
        "_अगर आपने गलती से 'नहीं' चुना, तो *मैं प्लंबर / प्लंबिंग कॉन्ट्रैक्टर हूँ* लिखें।_"
    ),
    "marathi": (
        "कृपया लक्षात घ्या की ही सुविधा फक्त सिन्टेक्स डिस्ट्रिब्युटर्स / प्लंबर / प्लंबिंग कॉन्ट्रॅक्टर साठी आहे.\n\n"
        "दुर्दैवाने, आम्ही तुमच्यासाठी पुढे जाऊ शकत नाही.\n\n"
        "येथे आल्याबद्दल धन्यवाद!\nतुमचा दिवस छान जावो! 😇\n\n"
        "_जर तुम्ही चुकून 'नाही' निवडले असेल तर *मी प्लंबर / प्लंबिंग कॉन्ट्रॅक्टर आहे* लिहा._"
    ),
    "hinglish": (
        "Please note karo ki yeh feature sirf Sintex Distributor / Plembar / Plumbing Thekedar ke liye hai.\n\n"
        "Duurbhagyavash, hum aage aapki madad nahi kar sakte.\n\n"
        "Yahan aane ke liye shukriya!\nAapka din achha ho! 😇\n\n"
        "_Agar aapne galti se 'Nahi' chuna, toh *Main plumber / plumbing contractor hoon* likhein._"
    ),
}

# ── LANGUAGE SELECTION HELPERS ────────────────────────────────────────────────

_LANGUAGE_PICK_MSG = (
    "Please select your preferred language / कृपया अपनी पसंदीदा भाषा चुनें:\n\n"
    "1️⃣ English\n"
    "2️⃣ Hindi (हिंदी)\n"
    "3️⃣ Marathi (मराठी)\n"
    "4️⃣ Hinglish\n\n"
    "Reply with the number (1, 2, 3 or 4) / नंबर भेजें (1, 2, 3 या 4)"
)

_LANGUAGE_REASK_MSG = (
    "Please reply with *1, 2, 3 or 4* to select your language 👇\n\n"
    "1️⃣ English\n"
    "2️⃣ Hindi (हिंदी)\n"
    "3️⃣ Marathi (मराठी)\n"
    "4️⃣ Hinglish"
)

_LANG_CONFIRMATIONS_REGISTERED: dict[str, str] = {
    "english": (
        "Great! Language set to *English*.\n\n"
        "Welcome to Sintex!\n\n"
        "We are excited to partner with you & look forward to a successful journey together.\n\n"
        "What would you like to do today?\n\n"
        "1. My Rewards\n"
        "2. Upload Purchase\n"
        "3. Product Help\n"
        "4. Support"
    ),
    "hindi": (
        "ठीक है! भाषा *हिंदी* में सेट की गई।\n\n"
        "स्वागत है सिंटेक्स में!\n\n"
        "हम आपके साथ जुड़कर बहुत खुश हैं और सफल सफर की उम्मीद करते हैं।\n\n"
        "आज आप क्या करना चाहेंगे?\n\n"
        "1. मेरे रिवॉर्ड्स\n"
        "2. खरीद अपलोड करें\n"
        "3. प्रोडक्ट हेल्प\n"
        "4. सपोर्ट"
    ),
    "marathi": (
        "ठीक आहे! भाषा *मराठी* मध्ये सेट केली.\n\n"
        "सिंटेक्स मध्ये स्वागतम!\n\n"
        "आम्हाला तुमच्या सोबत भागीदारी करून खूप आनंद झाला आहे आणि यशस्वी प्रवासाची अपेक्षा आहे.\n\n"
        "आज तुम्ही काय करणार आहात?\n\n"
        "1. माझे रिवॉर्ड्स\n"
        "2. खरेदी अपलोड करा\n"
        "3. प्रोडक्ट मदत\n"
        "4. सहाय्य"
    ),
    "hinglish": (
        "Theek hai! Language *Hinglish* mein set ki gayi.\n\n"
        "Sintex mein swagat hai!\n\n"
        "Hum aapke saath judkar bahut khush hain aur safal safar ki umeed karte hain.\n\n"
        "Aaj aap kya karna chahenge?\n\n"
        "1. Mere Rewards\n"
        "2. Purchase Upload\n"
        "3. Product Help\n"
        "4. Support"
    ),
}

_LANG_CONFIRMATIONS_UNREGISTERED: dict[str, str] = {
    "english":  "Great! Language set to *English*.\n\nAre you a plumber / plumbing contractor? Reply with the number:\n\n1. Yes\n2. No",
    "hindi":    "ठीक है! भाषा *हिंदी* में सेट की गई।\n\nक्या आप प्लंबर / प्लंबिंग कॉन्ट्रैक्टर हैं? नंबर भेजें:\n\n1. हाँ\n2. नहीं",
    "marathi":  "ठीक आहे! भाषा *मराठी* मध्ये सेट केली.\n\nतुम्ही प्लंबर / प्लंबिंग कॉन्ट्रॅक्टर आहात का? नंबर पाठवा:\n\n1. होय\n2. नाही",
    "hinglish": "Theek hai! Language *Hinglish* mein set ki gayi.\n\nKya aap plumber / plumbing contractor hain? Number bhejo:\n\n1. Haan\n2. Nahi",
}

# All reasonable ways a user might indicate their language choice.
# Keys are lowercased before lookup.
_LANG_REPLY_MAP: dict[str, str] = {
    # numbers
    "1": "english", "2": "hindi", "3": "marathi", "4": "hinglish",
    # english variants
    "english": "english", "eng": "english", "en": "english", "e": "english",
    # hindi variants
    "hindi": "hindi", "hin": "hindi", "hi": "hindi", "h": "hindi",
    "हिंदी": "hindi", "हिन्दी": "hindi", "hindhi": "hindi", "hind": "hindi",
    # marathi variants
    "marathi": "marathi", "mar": "marathi", "mr": "marathi", "m": "marathi",
    "मराठी": "marathi", "marathi": "marathi", "marathhi": "marathi",
    # hinglish variants
    "hinglish": "hinglish", "hing": "hinglish", "hng": "hinglish",
    "hinglesh": "hinglish", "hingliss": "hinglish", "hinglih": "hinglish",
}


def _parse_language_reply(message: str) -> str | None:
    return _LANG_REPLY_MAP.get(message.strip().lower())


@router.post("", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat_endpoint(
    request: ChatRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:

    logger.info(f"[/chat][mobile={request.mobile_number}] incoming payload: {request.model_dump()}")

    # ── 0. NORMALISE LANGUAGE ────────────────────────────────────
    # Language is optional in the payload now — unregistered users with no
    # DB language will be asked to choose. Fall back to "english" only for
    # registered users or sessions where the language is already stored.
    request_language = (request.language or "english").strip().lower()

    # ── 1. USER UPSERT ───────────────────────────────────────────
    existing_user = await crud.get_user_by_mobile(
        db=db,
        mobile_number=request.mobile_number
    )

    previously_registered = existing_user.is_registered if existing_user else False
    stored_user_id = (
        existing_user.user_id_evolve
        if existing_user and is_valid_user_id_evolve(existing_user.user_id_evolve)
        else None
    )

    # Create/load the local user first, but deliberately defer Evolve member
    # validation until after the plumber and language gates.
    user = await crud.upsert_user(
        db=db,
        mobile_number=request.mobile_number,
        user_id_evolve=stored_user_id,
    )
    just_registered_now = False

    # ── 2. CONVERSATION ──────────────────────────────────────────
    conversation = await crud.get_or_create_conversation(db=db, user_id=user.id)

    # Per-request context prefix used in all downstream log lines so each
    # log can be tied back to a specific user + conversation.
    log_ctx = f"[user_id={user.id} conv_id={conversation.id}]"
    trace_id = bind_trace_context(
        conversation_id=conversation.id,
        user_id=user.id,
        mobile_number=request.mobile_number,
    )
    logger.info(f"{log_ctx} resolved user (mobile={request.mobile_number}, is_registered={user.is_registered})")
    logger.info(f"{log_ctx} [TRACE] trace_id={trace_id}")

    # ── 2.5. LANGUAGE-SELECTION GATE ─────────────────────────────
    # Ask ANY user (registered or not) their preferred language whenever
    # no language is stored in the conversation DB yet.
    needs_language_ask = not getattr(conversation, "language", None)

    # ── SESSION RESUME CHECK (5 MIN INACTIVITY) ─────────────────
    TIMEOUT_MINUTES = 5

    last_assistant_message_before_request = await crud.get_last_assistant_message(
        db=db,
        conversation_id=conversation.id
    )

    is_session_resumed = False

    if (
        last_assistant_message_before_request
        and last_assistant_message_before_request.created_at
    ):
        now = datetime.now(timezone.utc)
        last_assistant_at = last_assistant_message_before_request.created_at
        if last_assistant_at.tzinfo is None:
            last_assistant_at = last_assistant_at.replace(tzinfo=timezone.utc)
        diff = now - last_assistant_at

        if diff > timedelta(minutes=TIMEOUT_MINUTES):
            is_session_resumed = True
            logger.info(
                f"{log_ctx} [SESSION RESET] last assistant response was "
                f"{diff.total_seconds() / 60:.1f} minutes ago; "
                "prior LLM history will be omitted"
            )

    # ── 3. SET LANGUAGE ──────────────────────────────────────────
    if needs_language_ask:
        # Don't persist request language yet; we will ask the user to choose.
        effective_language = request_language  # temporary fallback for this turn
    else:
        effective_language = (
            conversation.language
            if getattr(conversation, "language", None)
            else request_language
        )

        if not getattr(conversation, "language", None):
            await crud.set_conversation_language(
                db=db,
                conversation_id=conversation.id,
                language=request_language
            )
            conversation.language = request_language
            effective_language = request_language

    # ── 4. SAVE USER MESSAGE ─────────────────────────────────────
    # When the user sends ONLY an image (no text), WATI delivers an empty
    # message. Substitute a clear sentinel so the LLM understands the user
    # responded to the photo question with an image — not a fresh "start".
    _raw_attachment = _sanitize_attachment(request.attachment)
    if not request.message and _raw_attachment:
        user_message = "[image sent]"
    else:
        user_message = request.message or "start"

    _log_user_msg(conversation.id, user_message)

    await crud.save_message(
        db=db,
        conversation_id=conversation.id,
        user_id=user.id,
        sender="user",
        message=user_message,
    )

    # ── 4.5. PROFESSION CHECK (FIRST GATE) ───────────────────────
    # Every user must confirm they are a plumber before language selection or
    # Evolve member validation. A stored member ID does not bypass this gate.
    if user.is_plumber is None:
        prof_lang = (
            getattr(conversation, "language", None) or request_language or "english"
        ).lower()

        if conversation.stage != ConversationStage.PROFESSION_PENDING:
            await crud.set_conversation_stage(
                db, conversation.id, ConversationStage.PROFESSION_PENDING
            )
            prof_reply = _PROFESSION_ASK.get(
                prof_lang, _PROFESSION_ASK["english"]
            )
        else:
            is_plumber_val = await classify_plumber_reply(
                chatbot_orchestrator.llm, user_message
            )
            if is_plumber_val is None:
                prof_reply = _PROFESSION_REASK.get(
                    prof_lang, _PROFESSION_REASK["english"]
                )
            else:
                await crud.set_user_is_plumber(db, user.id, is_plumber_val)
                user.is_plumber = is_plumber_val
                await crud.set_conversation_stage(
                    db, conversation.id, ConversationStage.MEMBER_CHECK
                )
                prof_reply = (
                    None
                    if is_plumber_val
                    else _NOT_PLUMBER_BLOCKED.get(
                        prof_lang, _NOT_PLUMBER_BLOCKED["english"]
                    )
                )

        if prof_reply is not None:
            await crud.save_message(
                db=db,
                conversation_id=conversation.id,
                user_id=user.id,
                sender="assistant",
                message=prof_reply,
            )
            history_rows_prof = await crud.get_recent_messages(
                db=db, conversation_id=conversation.id, limit=50
            )
            _log_bot_msg(conversation.id, "profession", prof_reply)
            return ChatResponse(
                conversation_id=conversation.id,
                response=prof_reply,
                history=[
                    {
                        "sender": r.sender,
                        "message": r.message,
                        "created_at": (
                            r.created_at.isoformat()
                            if hasattr(r, "created_at")
                            else None
                        ),
                    }
                    for r in history_rows_prof
                ],
                status="active",
                language_change_requested=False,
                target_language=None,
                user_id_evolve=None,
                user_id_evolve_present=False,
            )

    # Users who previously answered "No" remain blocked unless they explicitly
    # correct that answer. This gate also runs before language/member lookup.
    if user.is_plumber is False:
        prof_lang = (
            getattr(conversation, "language", None) or request_language or "english"
        ).lower()
        is_correction = await classify_correction_intent(
            chatbot_orchestrator.llm, user_message
        )

        if is_correction:
            await crud.set_user_is_plumber(db, user.id, None)
            user.is_plumber = None
            await crud.set_conversation_stage(
                db, conversation.id, ConversationStage.PROFESSION_PENDING
            )
            blocked_reply = _PROFESSION_ASK.get(
                prof_lang, _PROFESSION_ASK["english"]
            )
        else:
            blocked_reply = _NOT_PLUMBER_BLOCKED.get(
                prof_lang, _NOT_PLUMBER_BLOCKED["english"]
            )

        await crud.save_message(
            db=db,
            conversation_id=conversation.id,
            user_id=user.id,
            sender="assistant",
            message=blocked_reply,
        )
        history_rows_blocked = await crud.get_recent_messages(
            db=db, conversation_id=conversation.id, limit=50
        )
        _log_bot_msg(conversation.id, "non_plumber_gate", blocked_reply)
        return ChatResponse(
            conversation_id=conversation.id,
            response=blocked_reply,
            history=[
                {
                    "sender": r.sender,
                    "message": r.message,
                    "created_at": (
                        r.created_at.isoformat()
                        if hasattr(r, "created_at")
                        else None
                    ),
                }
                for r in history_rows_blocked
            ],
            status="active",
            language_change_requested=False,
            target_language=None,
            user_id_evolve=None,
            user_id_evolve_present=False,
        )

    # ── 4.6. LANGUAGE SELECTION HANDLER (SECOND GATE) ────────────
    if needs_language_ask:
        lang_reply: str | None = None

        if conversation.stage == ConversationStage.LANGUAGE_PENDING:
            lang_reply = _parse_language_reply(user_message)
            if lang_reply:
                await crud.set_conversation_language(
                    db=db, conversation_id=conversation.id, language=lang_reply
                )
                conversation.language = lang_reply
                effective_language = lang_reply
                await crud.set_conversation_stage(
                    db, conversation.id, ConversationStage.MEMBER_CHECK
                )

        if lang_reply is None:
            if conversation.stage != ConversationStage.LANGUAGE_PENDING:
                # First time asking — show full prompt
                await crud.set_conversation_stage(
                    db, conversation.id, ConversationStage.LANGUAGE_PENDING
                )
                lang_assistant_reply = _LANGUAGE_PICK_MSG
            else:
                # Already asked but user sent something unrecognised — re-ask with guidance
                lang_assistant_reply = _LANGUAGE_REASK_MSG
            await crud.save_message(
                db=db,
                conversation_id=conversation.id,
                user_id=user.id,
                sender="assistant",
                message=lang_assistant_reply,
            )
            history_rows_lang = await crud.get_recent_messages(
                db=db, conversation_id=conversation.id, limit=50
            )
            history_payload_lang = [
                {
                    "sender": r.sender,
                    "message": r.message,
                    "created_at": (
                        r.created_at.isoformat()
                        if hasattr(r, "created_at")
                        else None
                    ),
                }
                for r in history_rows_lang
            ]
            _log_bot_msg(conversation.id, "language", lang_assistant_reply)
            return ChatResponse(
                conversation_id=conversation.id,
                response=lang_assistant_reply,
                history=history_payload_lang,
                status="active",
                language_change_requested=False,
                target_language=None,
                user_id_evolve=None,
                user_id_evolve_present=False,
            )

    # ── 4.7. MEMBER LOOKUP (THIRD GATE) ──────────────────────────
    # This is reached only after plumber confirmation and language selection.
    # Use the database member ID when present; otherwise validate by mobile.
    resolved_user_id = (
        user.user_id_evolve
        if is_valid_user_id_evolve(user.user_id_evolve)
        else None
    )
    if (
        not resolved_user_id
        and conversation.stage != ConversationStage.REGISTRATION_FLOW
    ):
        try:
            validation = await validate_member_by_mobile(request.mobile_number)
        except MemberValidationError as exc:
            logger.error(
                "[MEMBER VALIDATION] unable to resolve user | mobile=%s",
                request.mobile_number,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to validate membership right now. Please try again.",
            ) from exc
        resolved_user_id = validation.member_id

    user = await crud.upsert_user(
        db=db,
        mobile_number=request.mobile_number,
        user_id_evolve=resolved_user_id,
    )
    just_registered_now = bool(resolved_user_id) and not previously_registered

    # ── 5. FORCE STAGE FROM USER STATE ───────────────────────────
    is_registered_user = bool(user.user_id_evolve)
    completed_onboarding_gates = (
        conversation.stage == ConversationStage.MEMBER_CHECK
    )
    target_stage = (
        ConversationStage.NORMAL
        if is_registered_user
        else ConversationStage.REGISTRATION_FLOW
    )
    if conversation.stage != target_stage:
        await crud.set_conversation_stage(
            db, conversation.id, target_stage
        )
        conversation.stage = target_stage

    # When the ordered gates have just resolved an existing member, suppress
    # conversation history and show the main menu immediately.
    force_menu = is_registered_user and completed_onboarding_gates
    force_registration_resume = False

    if is_session_resumed:
        if is_registered_user:
            force_menu = True
        else:
            force_registration_resume = True

    if user_message.lower() in ["hi", "hello", "start"]:
        if is_registered_user:
            force_menu = True

    # ── 6. BUILD CONTEXT FOR LANGUAGE DETECTION ──────────────────
    history_rows = await crud.get_recent_messages(
        db=db,
        conversation_id=conversation.id,
        limit=25,
    )

    history = [
        {"sender": row.sender, "message": row.message}
        for row in history_rows
        if row.sender != "user" or row.message != request.message
    ]

    # A timed-out session starts with clean LLM context. Keep the rows in the
    # database for API/audit history, but do not expose them to language
    # detection or the chat agent. Registered users receive the main menu;
    # unregistered users remain behind the mandatory registration gate.
    if is_session_resumed:
        history = []

    last_messages = history[-10:]

    formatted_context = []
    for msg in last_messages:
        if msg["sender"] == "user":
            formatted_context.append({"role": "user", "content": msg["message"]})
        else:
            formatted_context.append({"role": "assistant", "content": msg["message"]})

    # ── 7. LANGUAGE CHANGE DETECTION ─────────────────────────────
    lang_result = await detect_intent_and_language_change_llm(
        chatbot_orchestrator.llm,
        user_message,
        formatted_context
    )

    intent = lang_result.get("intent", "allow")
    language_change_requested = lang_result.get("language_change_requested", False)
    target_language = lang_result.get("target_language")

    SUPPORTED_LANGS = {"english", "hindi", "marathi", "hinglish"}

    # Nullify an unrecognised target language (e.g. "urdu"), but keep
    # language_change_requested=True when target_language is null —
    # that means the user wants to switch but hasn't said which language yet
    # (we'll show them the selection menu in §8).
    if target_language is not None and target_language not in SUPPORTED_LANGS:
        target_language = None
        language_change_requested = False

    # ── 8. APPLY LANGUAGE CHANGE IF DETECTED ─────────────────────
    if language_change_requested and not target_language:
        # User wants to change language but didn't specify which one.
        # Show the language selection menu and wait for their pick.
        # We do NOT reset conversation stage — the user will return to
        # whatever they were doing after picking the new language.
        await crud.set_conversation_language(
            db=db,
            conversation_id=conversation.id,
            language=None,
        )
        conversation.language = None
        await crud.set_conversation_stage(
            db, conversation.id, ConversationStage.LANGUAGE_PENDING
        )

        lang_menu_reply = _LANGUAGE_PICK_MSG

        await crud.save_message(
            db=db,
            conversation_id=conversation.id,
            user_id=user.id,
            sender="assistant",
            message=lang_menu_reply,
        )

        history_rows_lang_change = await crud.get_recent_messages(
            db=db, conversation_id=conversation.id, limit=50
        )
        history_payload_lang_change = [
            {
                "sender": r.sender,
                "message": r.message,
                "created_at": r.created_at.isoformat() if hasattr(r, "created_at") else None,
            }
            for r in history_rows_lang_change
        ]

        logger.info(f"{log_ctx} [LANGUAGE CHANGE] user requested language change (no target) → showing menu")
        _log_bot_msg(conversation.id, "language_change_menu", lang_menu_reply)

        return ChatResponse(
            conversation_id=conversation.id,
            response=lang_menu_reply,
            history=history_payload_lang_change,
            status="active",
            language_change_requested=True,
            target_language=None,
            user_id_evolve=None,
            user_id_evolve_present=False,
        )

    if (
        language_change_requested
        and target_language
        and conversation.language != target_language
    ):
        await crud.set_conversation_language(
            db=db,
            conversation_id=conversation.id,
            language=target_language
        )
        conversation.language = target_language
        effective_language = target_language

    final_language = conversation.language or request_language

    logger.info(
        f"{log_ctx} [LANGUAGE] request={request_language} | "
        f"conversation={conversation.language} | "
        f"change_requested={language_change_requested} | "
        f"target={target_language} | "
        f"final_sent_to_agent={final_language}"
    )

    # ── 9. LOAD PERSISTED DEALER FLOW STAGE ──────────────────────
    # Read dealer_flow_stage that was saved to conversation after the previous turn.
    # This tells the agent exactly where in the dealer selection flow the user is,
    # so it never re-asks for dealer name when a serial number is expected.
    persisted_dealer_flow_stage = getattr(conversation, "dealer_flow_stage", "") or ""

    # Reset dealer flow stage when user sends hi/hello/start (fresh session)
    # or when session is resumed by a registered user (force_menu resets context).
    if force_menu or user_message.lower() in ["hi", "hello", "start"]:
        persisted_dealer_flow_stage = ""

    logger.info(f"{log_ctx} [DEALER FLOW] stage from DB = '{persisted_dealer_flow_stage}'")

    # ── 9.5 UPLOAD-PURCHASE DETERMINISTIC HANDLER ─────────────────
    # The QR Scan and Create-Claim flows must produce an exact dealer_code
    # (no LLM rewriting), so they are handled by a small Python state
    # machine. The handler returns handled=False unless the user is in
    # the upload flow OR is just entering it; in those cases we skip the
    # LLM agent entirely.
    #
    # State for this flow lives inside conversation.match_results_json as
    # a JSON blob — see app.upload_flow.handler.UploadFlowState.

    # Find the most recent assistant message from history (used to detect
    # "user typed 2 right after the main menu").
    last_assistant_message = (
        ""
        if is_session_resumed
        else (
            last_assistant_message_before_request.message
            if last_assistant_message_before_request
            else ""
        )
    )

    # Read the JSON blob ONCE up front. Re-reading conversation.match_results_json
    # after any await db.commit() forces a lazy SQL reload, which inside the
    # async engine requires a greenlet that FastAPI's get_db() does not
    # provide → sqlalchemy.exc.MissingGreenlet.
    persisted_match_results_json = conversation.match_results_json or ""
    upload_state_json_in = persisted_match_results_json

    # When the user resumes after timeout / sends hi/hello/start, the
    # main-menu reset above also wipes any in-progress upload flow,
    # both in memory (passed to handler) and in the DB.
    if force_menu or user_message.lower() in ["hi", "hello", "start"]:
        upload_state_json_in = ""
        if persisted_match_results_json:
            await crud.set_match_results_json(
                db=db,
                conversation_id=conversation.id,
                value=None,
            )
            persisted_match_results_json = ""

    upload_result_state_json_in = upload_state_json_in  # alias for clarity below

    # ── Compute the LLM-classified entry intent for the upload flow ──
    #
    # Why we do this here (and not inside the handler):
    #   * The classifier needs the LLM client, which is provided by
    #     chatbot_orchestrator. Keeping the handler LLM-free preserves
    #     its testability (the smoke test stays pure-Python).
    #   * The classifier is stage-aware; we already know the stage from
    #     the JSON blob we just loaded above.
    #   * The classifier's cheap path (numeric input) means most turns
    #     skip the LLM call entirely.
    #
    # Two layered checks:
    #   1. If the user typed "2" right after the main menu, that means
    #      "open Upload Purchase" — we bypass the classifier entirely
    #      because this case is unambiguous and deterministic.
    #   2. Otherwise we ask the classifier.
    _peek_state = upload_flow_handler.UploadFlowState.from_json(
        upload_state_json_in
    )
    current_upload_stage = _peek_state.stage or ""

    # Cheap deterministic shortcut: digit "2" right after the main menu
    # means "open Upload Purchase" without needing the LLM.
    _msg_stripped = (user_message or "").strip().translate(
        str.maketrans("०१२३४५६७८९", "0123456789")
    )
    upload_entry_intent: str
    if (
        not current_upload_stage
        and _msg_stripped == "2"
        and upload_flow_handler._is_main_menu_text(last_assistant_message or "")
    ):
        upload_entry_intent = "open_submenu"
        logger.info(f"{log_ctx} [UPLOAD INTENT] deterministic main-menu pick: open_submenu")
    elif (
        current_upload_stage
        and upload_flow_handler._parse_numbered_choice(user_message) is not None
    ):
        # Numbered replies inside the deterministic upload state machine
        # never need LLM classification. In particular, dealer pagination
        # option 11 must always reach the handler unchanged.
        upload_entry_intent = "continue"
        logger.info(
            f"{log_ctx} [UPLOAD INTENT] deterministic numbered choice: continue"
        )
    else:
        upload_entry_intent = await classify_upload_intent(
            llm=chatbot_orchestrator.llm,
            user_message=user_message,
            current_stage=current_upload_stage,
            last_assistant_message=last_assistant_message or "",
        )

    upload_result = await upload_flow_handler.handle(
        user_message=user_message,
        language=final_language,
        user_id_evolve=user.user_id_evolve,
        mobile_number=user.mobile_number,
        raw_state_json=upload_state_json_in,
        last_assistant_message=last_assistant_message,
        scanner_base_url=_resolve_scanner_base_url(http_request),
        is_registered=user.is_registered,
        entry_intent=upload_entry_intent,
    )

    if upload_result.handled:
        logger.info(
            f"{log_ctx} [UPLOAD FLOW] handled deterministically | "
            f"end_of_flow={upload_result.end_of_flow}"
        )

        # Persist any state changes the handler asked for.
        if upload_result.flow_state_json is not None:
            conversation.match_results_json = upload_result.flow_state_json
            await crud.set_match_results_json(
                db=db,
                conversation_id=conversation.id,
                value=upload_result.flow_state_json,
            )

        if upload_result.clear_legacy_dealer_flow_stage:
            await crud.set_dealer_flow_stage(
                db=db,
                conversation_id=conversation.id,
                dealer_flow_stage="",
            )

        # Translate the reply via LLM when requested (e.g. claim result has English server message).
        final_reply = upload_result.assistant_reply
        if upload_result.translate_reply:
            _lang_instruction = {
                "hindi": "Translate the following message to Hindi (Devanagari script). Reply with only the translated message.",
                "marathi": "Translate the following message to Marathi (Devanagari script). Reply with only the translated message.",
                "hinglish": "Translate the following message to Hinglish (Roman Hindi — Hindi words written in English letters). Reply with only the translated message.",
                "english": None,
            }.get(final_language)
            if _lang_instruction:
                try:
                    from langchain_core.messages import SystemMessage as _SysMsg, HumanMessage as _HumanMsg
                    _translation_result = await chatbot_orchestrator.llm.ainvoke([
                        _SysMsg(content=_lang_instruction),
                        _HumanMsg(content=upload_result.assistant_reply),
                    ])
                    final_reply = _translation_result.content.strip()
                    logger.info(f"{log_ctx} [UPLOAD FLOW] claim reply translated to {final_language}")
                except Exception as _te:
                    logger.warning(f"{log_ctx} [UPLOAD FLOW] translation failed, using original: {_te}")
                    final_reply = upload_result.assistant_reply

        # Save the assistant reply to the conversation history and return.
        await crud.save_message(
            db=db,
            conversation_id=conversation.id,
            user_id=user.id,
            sender="assistant",
            message=final_reply,
        )

        history_rows_after = await crud.get_recent_messages(
            db=db,
            conversation_id=conversation.id,
            limit=50,
        )
        history_payload = [
            {
                "sender": row.sender,
                "message": row.message,
                "created_at": row.created_at.isoformat() if hasattr(row, "created_at") else None,
            }
            for row in history_rows_after
        ]

        _log_bot_msg(conversation.id, "upload_flow", final_reply)

        return ChatResponse(
            conversation_id=conversation.id,
            response=final_reply,
            history=history_payload,
            status="active",
            language_change_requested=language_change_requested,
            target_language=target_language,
            user_id_evolve=None,
            user_id_evolve_present=False,
        )

    # Handler chose not to intercept. If it cleared upload-flow state
    # (e.g. user picked option 3 = claim status, which the LLM owns),
    # persist that clear so we don't leave stale state behind.
    if upload_result.flow_state_json is not None:
        conversation.match_results_json = upload_result.flow_state_json
        await crud.set_match_results_json(
            db=db,
            conversation_id=conversation.id,
            value=upload_result.flow_state_json,
        )
    if upload_result.clear_legacy_dealer_flow_stage:
        await crud.set_dealer_flow_stage(
            db=db,
            conversation_id=conversation.id,
            dealer_flow_stage="",
        )

    # ── 10. PREPARE PREFILL FOR AGENT ────────────────────────────
    prefill = {
        "language": final_language,
        "mobile_number": request.mobile_number,
        "is_registered": user.is_registered,
        "conversation_stage": conversation.stage.value,
        "just_registered_now": just_registered_now,
        "user_id_evolve": user.user_id_evolve,
        "is_session_resumed": is_session_resumed,
        "force_menu": force_menu,
        "force_registration_resume": force_registration_resume,
        "language_change_requested": language_change_requested,
        "target_language": target_language,
        "scanner_base_url": _resolve_scanner_base_url(http_request),
        "whatsapp_number": user.mobile_number,
        "dealer_flow_stage": persisted_dealer_flow_stage,  # ← PASS STAGE TO AGENT
        # WATI sends "NA" (and variants) as a sentinel when no file is attached.
        # Treat those as no attachment so the LLM never sees a fake filename.
        "attachment": _sanitize_attachment(request.attachment),
    }
    logger.info(f"{log_ctx} [PREFILL] attachment={prefill['attachment']!r}")
    # The match_results_json column is now used by the deterministic
    # upload-purchase handler; its content is meaningless to the LLM.
    # Pass through only the legacy list format (kept for backward-compat
    # in case some old conversation row still carries one); skip our
    # state blob.
    # Use the value captured at the top of the request (and any update the
    # upload-flow fall-through performed). Do NOT re-read
    # conversation.match_results_json here — see comment in section 9.5.
    if upload_result.flow_state_json is not None:
        raw_match = upload_result.flow_state_json
    else:
        raw_match = persisted_match_results_json

    legacy_match_results = ""
    if raw_match:
        try:
            parsed = json.loads(raw_match)
            if isinstance(parsed, list):
                legacy_match_results = raw_match
        except Exception:
            legacy_match_results = ""
    prefill["match_results_json"] = legacy_match_results

    flow = "registration" if conversation.stage == ConversationStage.REGISTRATION_FLOW else "default"

    # ── 11. CALL AGENT ───────────────────────────────────────────
    try:
        agent_result = await chatbot_orchestrator.stream_response(
            conversation_id=conversation.id,
            user_message=user_message,
            history=history,
            flow=flow,
            prefill=prefill,
        )

    except Exception as exc:
        logger.error(f"{log_ctx} [ERROR] Agent failed | {str(exc)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agent error",
        )

    assistant_reply = agent_result["response"]
    tool_traces = agent_result.get("tool_traces", [])
    # ── OVERRIDE QR RESPONSE (REMOVE LLM DEPENDENCY) ───────────────
    for trace in tool_traces:
        if trace.get("type") == "tool_result":
            output = trace.get("output", {})

            if isinstance(output, dict) and output.get("dealer_flow_stage") == "dealer_selected":

                dealer_code = output.get("dealer_code")

                # 🔥 BUILD URL IN BACKEND
                scanner_url = (
                    f"https://api.wel-wise.com/sintex_agent_uat/scanner"
                    f"?user_id_evolve={user.user_id_evolve}"
                    f"&whatsapp_number={user.mobile_number}"
                    f"&dealer_code={dealer_code}"
                )

                # 🌐 LANGUAGE HANDLING
                lang = (conversation.language or "english").lower()

                if lang == "hindi":
                    assistant_reply = f"QR कोड स्कैन करने के लिए यह लिंक खोलें:\n{scanner_url}"
                elif lang == "hinglish":
                    assistant_reply = f"QR scan karne ke liye yeh link open karein:\n{scanner_url}"
                elif lang == "marathi":
                    assistant_reply = f"QR स्कॅन करण्यासाठी हा लिंक उघडा:\n{scanner_url}"
                else:
                    assistant_reply = f"QR code scan link is ready:\n{scanner_url}"

                logger.info(f"{log_ctx} [QR URL] dealer_code={dealer_code} | url={scanner_url}")
                break  # 🔥 IMPORTANT: stop after first match

    # ── 12. EXTRACT DEALER FLOW STAGE FROM THIS TURN'S TOOL TRACES ──
    # update_dealer_flow_stage() scans tool_traces for find_dealer_tool results
    # and returns an updated prefill with the new dealer_flow_stage value.
    # We then save it to the conversation so the next turn picks it up.
    updated_prefill = update_dealer_flow_stage(prefill, tool_traces)
    # ── STORE match_results_json FROM TOOL ──
    for trace in tool_traces:
        if trace.get("type") == "tool_result":
            output = trace.get("output", {})

            if isinstance(output, dict) and "match_results_json" in output:
                conversation.match_results_json = output["match_results_json"]
                await db.commit()
    new_dealer_flow_stage = updated_prefill.get("dealer_flow_stage", "")

    if new_dealer_flow_stage != persisted_dealer_flow_stage:
        logger.info(
            f"{log_ctx} [DEALER FLOW] stage transition: "
            f"'{persisted_dealer_flow_stage}' → '{new_dealer_flow_stage}'"
        )

    # Save new dealer_flow_stage to the conversation row in DB
    # so it is available on the next HTTP request.
    await crud.set_dealer_flow_stage(
        db=db,
        conversation_id=conversation.id,
        dealer_flow_stage=new_dealer_flow_stage,
    )
    if new_dealer_flow_stage == "dealer_selected":
        conversation.match_results_json = None
        await db.commit()

    # ── 13. EXTRACT USER_ID FROM TOOL TRACES ─────────────────────
    user_id_from_tool = None
    last_tool_name = None

    for trace in tool_traces:
        if trace.get("type") == "tool_call":
            last_tool_name = trace.get("tool_name")

        elif trace.get("type") == "tool_result":
            output = trace.get("output", {})

            if last_tool_name == "submit_user_registration":
                if isinstance(output, str):
                    try:
                        output = json.loads(output)
                    except Exception:
                        logger.warning(f"{log_ctx} [TOOL OUTPUT PARSE FAILED] output={output}")
                        output = {}

                if isinstance(output, dict):
                    user_id_from_tool = output.get("user_id")

                break

    # ── SAVE USER_ID TO DB ────────────────────────────────────────
    if user_id_from_tool:
        user.user_id_evolve = user_id_from_tool
        user.is_registered = True
        await db.commit()

    is_complete = agent_result.get("is_complete", False)

    # ── 14. SAVE ASSISTANT RESPONSE ──────────────────────────────
    await crud.save_message(
        db=db,
        conversation_id=conversation.id,
        user_id=user.id,
        sender="assistant",
        message=assistant_reply,
    )

    # ── 15. HANDLE COMPLETION ────────────────────────────────────
    if is_complete and conversation.stage == ConversationStage.REGISTRATION_FLOW:
        await crud.set_conversation_stage(
            db, conversation.id, ConversationStage.NORMAL
        )
        conversation.stage = ConversationStage.NORMAL

    # ── 16. FINAL HISTORY ────────────────────────────────────────
    history_rows = await crud.get_recent_messages(
        db=db,
        conversation_id=conversation.id,
        limit=50,
    )

    history_payload = [
        {
            "sender": row.sender,
            "message": row.message,
            "created_at": row.created_at.isoformat() if hasattr(row, "created_at") else None
        }
        for row in history_rows
    ]

    chat_response = ChatResponse(
        conversation_id=conversation.id,
        response=assistant_reply,
        history=history_payload,
        status="active",
        language_change_requested=language_change_requested,
        target_language=target_language,
        user_id_evolve=user_id_from_tool,
        user_id_evolve_present=True if user_id_from_tool else False
    )

    _log_bot_msg(conversation.id, "llm_agent", assistant_reply)

    log_payload = chat_response.dict(exclude={"history", "response"})
    logger.info(f"{log_ctx} [CHAT RESPONSE] {json.dumps(log_payload, indent=2)}")

    return chat_response
