"""
upload_flow/intent.py

Small LLM-based intent classifier for the Upload Purchase flow.

Why a dedicated classifier
==========================
Earlier, the upload flow detected entry points via a regex list — "upload
purchase", "scan qr", "क्लेम बनाओ", and so on. Every time a user typed a
new variant ("Khareed upload kre", "mujhe QR scan karna hai", "claim
banwana hai bro"), the flow got stuck and we patched the regex.

This module replaces that regex list with a small, stage-aware LLM call.
The LLM understands meaning across English, Hindi, Marathi, Hinglish,
mixed scripts, typos, and mood-driven phrasing — so users can type in
whatever way they want, and we route them correctly.

Design properties
=================
1. **State-aware.** The classifier knows what stage the upload flow is
   currently at. The same message ("1") means different things at
   different stages:
       - main menu just shown   → "1" means rewards (NOT our flow)
       - submenu shown          → "1" means start_qr
       - serial selection stage → "1" means continue (pick dealer #1)
       - amount stage           → "1500" means continue (purchase amount)

2. **Cheap.** We only call the LLM when the message is non-trivial. For
   purely numeric or short canonical inputs ("1", "2", "३") there is no
   ambiguity given the stage — we bypass the LLM entirely and just
   return "continue" or the obvious entry intent.

3. **Conservative on errors.** If the LLM call fails, we return
   "continue" so the existing flow logic takes over. This means even on
   total LLM outage the flow still works the same way it did before
   the classifier existed (numeric inputs always work).

Returned intents
================
   "start_qr"       — user wants to scan a QR / upload a product code
   "start_claim"    — user wants to create / file a claim
   "start_status"   — user wants to check claim status
   "open_submenu"   — user wants the Upload Purchase area generally
                      (didn't say QR vs claim vs status)
   "exit"           — user wants to leave the upload flow (main menu,
                      back, cancel, switch to rewards, "never mind", etc.)
   "continue"       — user is responding inside the current stage
                      (firm name, serial number, amount, "yes/no", etc.)
   "none"           — no recognisable intent; let the caller decide
                      (typically the same as "continue" mid-flow, or
                      "skip handler" when no stage is active)
"""

from __future__ import annotations

import json
import re
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.utils.logger import get_logger

logger = get_logger(__name__)


VALID_INTENTS = {
    "start_qr",
    "start_claim",
    "start_status",
    "open_submenu",
    "exit",
    "continue",
    "none",
}


# Devanagari → ASCII for the cheap "is it just a number" check.
_DEV_TO_ASCII = str.maketrans("०१२३४५६७८९", "0123456789")


def _is_pure_int_or_short_amount(message: str) -> bool:
    """
    Cheap check: is the message just digits (in either script), possibly
    with commas/spaces? If so, the LLM call is unnecessary — the upload
    handler already knows how to interpret numeric input given the
    current stage.
    """
    s = (message or "").translate(_DEV_TO_ASCII).strip()
    if not s:
        return False
    s = s.replace(",", "").replace(" ", "")
    return bool(re.fullmatch(r"\d+(\.\d+)?", s))


# ──────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────

async def classify_upload_intent(
    *,
    llm,
    user_message: str,
    current_stage: str,
    last_assistant_message: str = "",
) -> str:
    """
    Classify a user message into one of VALID_INTENTS, given the upload
    flow's current stage.

    Args:
        llm: the chat model (chatbot_orchestrator.llm).
        user_message: raw user text in any language.
        current_stage: current upload-flow stage, or "" if no flow active.
            One of: "" | "submenu_shown" | "qr_awaiting_name" |
            "qr_awaiting_serial" | "claim_awaiting_name" |
            "claim_awaiting_serial" | "claim_awaiting_amount".
        last_assistant_message: most recent bot reply (used to help the
            LLM disambiguate "1" right after the main menu vs right after
            our submenu).

    Returns:
        One of VALID_INTENTS. Falls back to "continue" if the LLM errors
        and a flow is active, or "none" if no flow is active.
    """

    msg = (user_message or "").strip()
    if not msg:
        return "continue" if current_stage else "none"

    # ───── Cheap path: numeric inputs ─────
    # Numeric messages are unambiguous given the stage. No LLM needed.
    if _is_pure_int_or_short_amount(msg):
        if current_stage:
            # Inside a flow, numbers are always continuation
            # (submenu pick, serial pick, amount).
            return "continue"
        # No active flow + numeric message → let the chat route's main-menu
        # logic decide (this handler does not interpret main-menu picks).
        return "none"

    # ───── LLM path: free-form text ─────
    system_prompt = _build_system_prompt(
        current_stage=current_stage,
        last_assistant_message=last_assistant_message,
    )

    try:
        response = await llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=msg),
            ]
        )
        raw = (response.content or "").strip()
        logger.info(f"[upload_intent] raw={raw!r} stage={current_stage!r} msg={msg[:80]!r}")

        intent = _extract_intent(raw)
        if intent not in VALID_INTENTS:
            logger.warning(f"[upload_intent] unknown intent {intent!r}; defaulting")
            intent = "continue" if current_stage else "none"

        logger.info(f"[upload_intent] resolved intent={intent}")
        return intent

    except Exception:
        logger.exception("[upload_intent] LLM call failed; falling back")
        return "continue" if current_stage else "none"


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _extract_intent(raw: str) -> str:
    """
    Pull the intent label out of the LLM response. We expect strict JSON,
    but accept a bare label too so a stray newline or markdown fence
    doesn't break us.
    """
    if not raw:
        return ""

    # Try JSON first.
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return str(data.get("intent", "")).strip().lower()
    except Exception:
        pass

    # Fallback: scan the response for a known label.
    lowered = raw.lower()
    for label in VALID_INTENTS:
        if label in lowered:
            return label

    return ""


_STAGE_HINTS = {
    "": (
        "No upload flow is active right now. Decide whether the user is "
        "asking to enter the Upload Purchase area."
    ),
    "submenu_shown": (
        "We just showed the user the Upload Purchase sub-menu (QR / "
        "Claim / Status). They are expected to pick one. Numeric input "
        "would be a continuation, but they may also ask in free text."
    ),
    "qr_awaiting_name": (
        "We are inside the QR sub-flow and just asked the user for their "
        "dealer firm name. Anything that looks like a firm name is a "
        "continuation."
    ),
    "qr_awaiting_serial": (
        "We just showed the user a numbered list of dealer matches and "
        "asked them to pick one. A serial number is a continuation."
    ),
    "claim_awaiting_name": (
        "We are inside the Create Claim sub-flow and just asked the user "
        "for their dealer firm name. Anything that looks like a firm "
        "name is a continuation."
    ),
    "claim_awaiting_serial": (
        "We just showed the user a numbered list of dealer matches and "
        "asked them to pick one. A serial number is a continuation."
    ),
    "claim_awaiting_amount": (
        "We just asked the user for the purchase amount in rupees. Any "
        "amount-like text is a continuation."
    ),
}


def _build_system_prompt(*, current_stage: str, last_assistant_message: str) -> str:
    """Compose the stage-aware system prompt for the classifier."""

    stage_hint = _STAGE_HINTS.get(current_stage, _STAGE_HINTS[""])

    last_block = ""
    if last_assistant_message:
        snippet = last_assistant_message.strip()
        if len(snippet) > 600:
            snippet = snippet[:600] + " …"
        last_block = (
            "\nMost recent assistant message (for context):\n"
            f"<<<\n{snippet}\n>>>\n"
        )

    return f"""\
You are a tiny intent classifier for the Sintex chatbot's Upload Purchase flow.

Sintex users speak English, Hindi, Marathi, and Hinglish (Roman-script
Hindi), often with typos, slang, and mixed scripts. Your only job is to
output ONE of these intents, given the user's message and the current
flow stage:

  start_qr       — user wants to SCAN a QR code / upload a product code.
                   Examples in any language:
                     "scan qr", "qr scan karna hai", "qr code upload",
                     "मुझे QR स्कैन करना है", "QR उडवायचा आहे",
                     "i want to scan a code", "code scan karwa do"

  start_claim    — user wants to CREATE / FILE / RAISE a *purchase claim*
                   specifically inside the Upload Purchase flow.
                   Examples:
                     "create claim", "claim banao", "claim banwana hai",
                     "मुझे क्लेम बनाना है", "क्लेम तयार करा",
                     "make a claim", "claim raise kar do"
                   ⚠️  DO NOT use start_claim for support tickets, complaints,
                   or grievances — those are NOT purchase claims. Examples that
                   must NOT be start_claim:
                     "raise a ticket", "support ticket", "complaint",
                     "I have an issue", "raise a concern", "grievance",
                     "ticket banana hai", "mujhe complaint karni hai"

  start_status   — user wants to CHECK status of an existing claim.
                   Examples:
                     "claim status", "claim ka status", "मेरे क्लेम का स्टेटस",
                     "where is my claim", "claim kaha tak pohcha"

  open_submenu   — user wants the Upload Purchase area generically but
                   has NOT yet chosen QR vs claim vs status.
                   Examples:
                     "upload purchase", "purchase upload", "खरीद अपलोड",
                     "मुझे खरीद अपलोड करनी है", "khareed upload kre",
                     "purchase add karna hai", "i want to upload my bill"

  exit           — user wants to LEAVE the upload flow. Includes:
                     "main menu", "menu", "back", "home", "cancel",
                     "मुख्य मेनू", "वापस", "मेनू", "ghar wapas",
                     "rad karo", "i want rewards instead",
                     "मुझे रिवॉर्ड्स देखने हैं", "show me my balance",
                     "actually never mind", "let me go back"
                   Also use 'exit' if the user explicitly asks for a
                   DIFFERENT feature (rewards, find dealer, support)
                   while inside the upload flow — they want to leave.

  continue       — user is replying INSIDE the current stage with
                   data the stage is waiting for: a dealer firm name,
                   a serial number, an amount in rupees, "yes" / "no",
                   etc. When in doubt mid-flow, use 'continue'.

  none           — no recognisable intent in this context. Use this
                   only when no flow is active and the message is
                   clearly not about Upload Purchase (e.g. "hi",
                   "thanks", "what are sintex products").

CURRENT STAGE: {current_stage or '<no flow active>'}
{stage_hint}
{last_block}
RULES
=====
- Always pick exactly one label from the list above.
- If the user asks for QR / claim / status SPECIFICALLY by name, use
  start_qr / start_claim / start_status — do NOT use open_submenu.
- If the user is generic about uploading a purchase, use open_submenu.
- Mid-flow, prefer 'continue' over 'none' or 'open_submenu'.
- If the user asks to leave or switch to a different feature, use 'exit'.
- 'start_claim' means a PURCHASE CLAIM (uploading a bill/QR for rewards).
  It does NOT mean a support ticket, complaint, or grievance. Messages like
  "raise a ticket", "support ticket", "I have a complaint", "raise a concern",
  "ticket banana hai", "mujhe issue hai" must return 'none' — they belong to
  the Support feature (option 4 in the main menu), not the Upload Purchase flow.
- Do not invent labels. Output STRICT JSON only:

  {{"intent": "<one of: start_qr | start_claim | start_status | open_submenu | exit | continue | none>"}}
"""
