"""
upload_flow/handler.py

Deterministic state-machine handler for the Upload Purchase flow.

Why it exists:
The original implementation routed the entire QR + Create-Claim flow
through the LLM agent. That made dealer_code accuracy fragile because:
  * The LLM had to remember to pass `cached_dealers` JSON between turns.
  * The LLM had to call the right find_dealer_tool MODE in the right order.
  * The LLM could paraphrase or invent dealer_code values.
  * With ~500 dealers, prompt-side fuzzy matching was unreliable.

This module replaces all of that with a small, predictable state machine:

  ┌─────────────────────────────┐
  │  trigger from main menu /   │
  │  keyword like "upload..."   │
  └──────────────┬──────────────┘
                 │
        stage = submenu_shown
                 │
   user picks 1 (QR) | 2 (claim) | 3 (status)
        │             │             │
        ▼             ▼             ▼
  qr_awaiting     claim_awaiting   (returned to LLM —
   _name           _name            claim status flow
                                    is unchanged)
        │             │
   user types     user types
   firm name      firm name
        │             │
        ▼             ▼
  qr_awaiting     claim_awaiting
   _serial         _serial
        │             │
   user picks #   user picks #
        │             │
        ▼             ▼
   QR LINK         claim_awaiting
   READY (done)     _amount
                       │
                  user types ₹
                       │
                       ▼
                   CLAIM RESULT
                    (done)

Persistence:
The current stage and any in-progress dealer matches / selected dealer
info are stored as a single JSON blob in `Conversation.match_results_json`
(a Text column, no schema change needed). This is read at the start of
each request and updated at the end.

The handler returns:
  * `assistant_reply` — the text to show the user, in their language
  * `flow_state_json` — the new value to persist into match_results_json
  * `clear_dealer_flow_stage` — whether to clear the legacy
    `dealer_flow_stage` column on the conversation row

The chat route is responsible for actually persisting these values; the
handler is pure-ish (it does call APIs, but it does not touch the DB).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

from app.utils.logger import get_logger
from app.upload_flow import messages as M
from app.upload_flow.dealer_service import (
    PAGE_SIZE,
    create_claim,
    fetch_dealers,
    search_dealers,
)

logger = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────

# Canonical stage values held in `match_results_json["stage"]`.
STAGE_SUBMENU_SHOWN = "submenu_shown"
STAGE_QR_NAME = "qr_awaiting_name"
STAGE_QR_SERIAL = "qr_awaiting_serial"
STAGE_CLAIM_NAME = "claim_awaiting_name"
STAGE_CLAIM_SERIAL = "claim_awaiting_serial"
STAGE_CLAIM_AMOUNT = "claim_awaiting_amount"

UPLOAD_STAGES = {
    STAGE_SUBMENU_SHOWN,
    STAGE_QR_NAME,
    STAGE_QR_SERIAL,
    STAGE_CLAIM_NAME,
    STAGE_CLAIM_SERIAL,
    STAGE_CLAIM_AMOUNT,
}


# Devanagari → ASCII digit map. Users type pincodes / amounts / serial
# numbers in either script; we always normalise before validating.
_DEV_TO_ASCII = str.maketrans("०१२३४५६७८९", "0123456789")


def _to_ascii_digits(text: str) -> str:
    return (text or "").translate(_DEV_TO_ASCII).strip()


def _is_pure_int(text: str) -> Optional[int]:
    """Return int if `text` is purely an integer (after Devanagari → ASCII), else None."""
    raw = _to_ascii_digits(text)
    if not raw:
        return None
    if not re.fullmatch(r"-?\d+", raw):
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _parse_numbered_choice(text: str) -> Optional[int]:
    """
    Parse a numbered-menu reply without involving the LLM.

    Besides a bare number, accept common WhatsApp replies such as
    ``11.``, ``11)``, ``#11``, ``option 11`` and ``11th``. This is used
    only at stages that explicitly expect a numbered choice.
    """
    raw = _to_ascii_digits(text).lower()
    match = re.fullmatch(
        r"\s*(?:option|opt|number|no\.?|#)?\s*(\d+)"
        r"(?:st|nd|rd|th)?\s*[\.\)]?\s*",
        raw,
    )
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _is_positive_amount(text: str) -> Optional[float]:
    """Return float if text is a positive number (commas / spaces ok), else None."""
    raw = _to_ascii_digits(text).replace(",", "").replace(" ", "")
    if not raw:
        return None
    if not re.fullmatch(r"\d+(\.\d+)?", raw):
        return None
    try:
        val = float(raw)
    except ValueError:
        return None
    return val if val > 0 else None


# ──────────────────────────────────────────────────────────────────────
# STATE BLOB
# ──────────────────────────────────────────────────────────────────────

@dataclass
class UploadFlowState:
    """In-memory representation of the JSON blob persisted to DB."""
    stage: str = ""
    # Full ranked fuzzy-match list — stored once, paginated on display.
    all_matches: List[Dict[str, Any]] = None
    # Current page index (0-based). Page N shows all_matches[N*PAGE_SIZE : (N+1)*PAGE_SIZE].
    page: int = 0
    selected_firm_name: str = ""
    selected_dealer_code: str = ""

    # ── convenience ──────────────────────────────────────────────

    def current_page_matches(self) -> List[Dict[str, Any]]:
        """Return the slice of all_matches for the current page, 1-based serials."""
        all_m = self.all_matches or []
        start = self.page * PAGE_SIZE
        slice_ = all_m[start: start + PAGE_SIZE]
        return [
            {**row, "serial": idx}
            for idx, row in enumerate(slice_, start=1)
        ]

    def has_next_page(self) -> bool:
        all_m = self.all_matches or []
        return (self.page + 1) * PAGE_SIZE < len(all_m)

    # ── serialisation ─────────────────────────────────────────────

    @classmethod
    def from_json(cls, raw: Optional[str]) -> "UploadFlowState":
        if not raw:
            return cls()

        try:
            data = json.loads(raw)
        except Exception:
            return cls()

        if not isinstance(data, dict):
            return cls()

        stage = str(data.get("stage", "") or "")

        all_matches = data.get("all_matches") or []
        if not isinstance(all_matches, list):
            all_matches = []

        # Back-compat: old blobs stored `matches` (already-paginated slice).
        # Treat it as all_matches so existing in-flight sessions don't break.
        if not all_matches:
            legacy = data.get("matches") or []
            if isinstance(legacy, list):
                all_matches = legacy

        try:
            page = int(data.get("page", 0))
        except (TypeError, ValueError):
            page = 0

        return cls(
            stage=stage,
            all_matches=all_matches,
            page=page,
            selected_firm_name=str(data.get("selected_firm_name") or ""),
            selected_dealer_code=str(data.get("selected_dealer_code") or ""),
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "stage": self.stage,
                "all_matches": self.all_matches or [],
                "page": self.page,
                "selected_firm_name": self.selected_firm_name,
                "selected_dealer_code": self.selected_dealer_code,
            },
            ensure_ascii=False,
        )

    def clear(self) -> None:
        self.stage = ""
        self.all_matches = []
        self.page = 0
        self.selected_firm_name = ""
        self.selected_dealer_code = ""


# ──────────────────────────────────────────────────────────────────────
# RESULT
# ──────────────────────────────────────────────────────────────────────

@dataclass
class HandlerResult:
    handled: bool                          # if False, fall through to LLM agent
    assistant_reply: str = ""              # text to send the user
    flow_state_json: Optional[str] = None  # value to persist into match_results_json (None = no change)
    clear_legacy_dealer_flow_stage: bool = False  # whether to set conversation.dealer_flow_stage = ""
    end_of_flow: bool = False              # true when QR shown / claim created / cancelled
    translate_reply: bool = False          # if True, chat route should translate assistant_reply via LLM


# ──────────────────────────────────────────────────────────────────────
# TRIGGER DETECTION
# ──────────────────────────────────────────────────────────────────────
#
# The upload flow used to detect entry points via a hand-written regex
# list ("upload purchase", "scan qr", "क्लेम बनाओ", and so on). That
# approach didn't scale: users type things in any of four languages with
# typos, slang, mood-driven phrasing, mixed scripts. Every new variant
# meant another patch to the regex.
#
# The new approach: the chat route runs a small LLM-based classifier
# (app/upload_flow/intent.py) before calling us, and passes us the
# resolved intent label as `entry_intent`. This file only knows how to
# *act* on those labels — it does not know how to detect them. That
# separation is the whole point of the refactor.
#
# Recognised entry-intent values (produced by the classifier):
#   "start_qr"      → user wants to scan a QR code
#   "start_claim"   → user wants to create a claim
#   "start_status"  → user wants to check claim status (LLM agent owns this)
#   "open_submenu" → user wants the upload area but hasn't picked yet
#   "exit"          → user wants to leave the upload flow
#   "continue"      → user is replying inside an active stage
#   "none"          → none of the above; not our concern
#
# We keep _is_main_menu_text() for a small backwards-compat path: if the
# main menu is on screen and the user types "2", the chat route still
# routes that here as `entry_intent="open_submenu"` — but the function
# itself is unused now and could be removed in a future cleanup.

# Entry-intent constants we route on.
_INTENT_START_QR = "start_qr"
_INTENT_START_CLAIM = "start_claim"
_INTENT_START_STATUS = "start_status"
_INTENT_OPEN_SUBMENU = "open_submenu"
_INTENT_EXIT = "exit"
_INTENT_CONTINUE = "continue"
_INTENT_NONE = "none"


def _is_main_menu_text(text: str) -> bool:
    """
    Detect whether a given assistant message looks like the main menu.
    Kept for backward compatibility — the new intent-driven routing
    does not rely on this directly, but the chat route may still use
    it as a sanity check.
    """
    if not text:
        return False

    options = {
        match.group(1): match.group(2).casefold()
        for match in re.finditer(r"(?m)^\s*([1-9])\s*[\.\)]\s*(.+?)\s*$", text)
    }

    reward_terms = (
        "my rewards",
        "mere rewards",
        "मेरे रिवॉर्ड्स",
        "माझे रिवॉर्ड्स",
    )
    upload_terms = (
        "upload purchase",
        "purchase upload",
        "खरीद अपलोड",
        "खरेदी अपलोड",
    )

    option_1 = options.get("1", "")
    option_2 = options.get("2", "")
    return (
        any(term in option_1 for term in reward_terms)
        and any(term in option_2 for term in upload_terms)
    )


# ──────────────────────────────────────────────────────────────────────
# PUBLIC ENTRY POINT
# ──────────────────────────────────────────────────────────────────────

async def handle(
    *,
    user_message: str,
    language: str,
    user_id_evolve: Optional[str],
    mobile_number: str,
    raw_state_json: Optional[str],
    last_assistant_message: Optional[str],
    scanner_base_url: str,
    is_registered: bool,
    entry_intent: str = "",
) -> HandlerResult:
    """
    Inspect the current upload-flow state plus the LLM-classified entry
    intent, advance the state machine, and return a HandlerResult.

    Routing:
      - Mid-flow + entry_intent == "exit"
            → clear state, hand off to LLM agent so it can satisfy the
              user's actual ask (main menu, rewards, support, ...).
      - Mid-flow + entry_intent in {"start_qr", "start_claim"}
            → user is changing their mind mid-flow ("actually let me
              do a claim instead"). Re-enter the right sub-flow.
      - Mid-flow + entry_intent in {"continue", "none", ""}
            → existing _advance() logic for the active stage.
      - No flow + entry_intent == "start_qr"
            → jump directly into the QR firm-name prompt.
      - No flow + entry_intent == "start_claim"
            → jump directly into the Claim firm-name prompt.
      - No flow + entry_intent == "start_status"
            → handed off to LLM agent (claim status is its job).
      - No flow + entry_intent == "open_submenu"
            → show the Upload Purchase sub-menu.
      - Anything else
            → handled=False, fall through to the LLM agent.

    `handled=False` means the chat route should run the LLM agent.
    `handled=True` means the chat route should return assistant_reply
    directly and persist any state changes.
    """

    state = UploadFlowState.from_json(raw_state_json)
    intent = (entry_intent or "").strip().lower()

    # ---------------- MID-FLOW: user wants to exit ----------------
    # The classifier marks "main menu" / "back" / "मुख्य मेनू" / "rewards
    # instead" / "actually never mind" / etc. as `exit`. We clear the
    # upload state and return handled=False so the LLM agent answers
    # the user's actual ask in their language.
    if state.stage in UPLOAD_STAGES and intent == _INTENT_EXIT:
        logger.info("[upload_flow] exit intent during stage=%s — clearing state", state.stage)
        state.clear()
        return HandlerResult(
            handled=False,                       # let LLM agent take over
            flow_state_json=state.to_json(),
            clear_legacy_dealer_flow_stage=True,
            end_of_flow=True,
        )

    # ---------------- MID-FLOW: user is switching sub-flow ----------------
    # User says "actually I want to scan a QR" while we're in the middle
    # of a Create-Claim flow (or vice versa). Reset to the right
    # sub-flow's starting stage.
    if state.stage in UPLOAD_STAGES and intent in (_INTENT_START_QR, _INTENT_START_CLAIM):
        next_stage = STAGE_QR_NAME if intent == _INTENT_START_QR else STAGE_CLAIM_NAME
        logger.info(
            "[upload_flow] sub-flow switch from stage=%s → %s",
            state.stage, next_stage,
        )
        state.all_matches = []
        state.page = 0
        state.selected_firm_name = ""
        state.selected_dealer_code = ""
        return await _enter_dealer_selection(
            state=state,
            next_stage=next_stage,
            language=language,
            user_id_evolve=user_id_evolve,
        )

    # ---------------- MID-FLOW: continue current stage ----------------
    if state.stage in UPLOAD_STAGES:
        return await _advance(
            state=state,
            user_message=user_message,
            language=language,
            user_id_evolve=user_id_evolve,
            mobile_number=mobile_number,
            scanner_base_url=scanner_base_url,
        )

    # ---------------- NOT IN FLOW ----------------
    if not is_registered:
        # Unregistered users must finish registration first; the LLM
        # owns that flow.
        return HandlerResult(handled=False)

    # Direct-jump into QR sub-flow.
    if intent == _INTENT_START_QR:
        return await _enter_dealer_selection(
            state=state,
            next_stage=STAGE_QR_NAME,
            language=language,
            user_id_evolve=user_id_evolve,
        )

    # Direct-jump into Create Claim sub-flow.
    if intent == _INTENT_START_CLAIM:
        return await _enter_dealer_selection(
            state=state,
            next_stage=STAGE_CLAIM_NAME,
            language=language,
            user_id_evolve=user_id_evolve,
        )

    # Generic Upload Purchase entry → show the sub-menu.
    if intent == _INTENT_OPEN_SUBMENU:
        state.stage = STAGE_SUBMENU_SHOWN
        state.all_matches = []
        state.page = 0
        state.selected_firm_name = ""
        state.selected_dealer_code = ""
        return HandlerResult(
            handled=True,
            assistant_reply=M.submenu(language),
            flow_state_json=state.to_json(),
            clear_legacy_dealer_flow_stage=True,
        )

    # Claim status flow stays on the LLM agent.
    if intent == _INTENT_START_STATUS:
        return HandlerResult(handled=False)

    # Anything else → LLM agent takes the turn.
    return HandlerResult(handled=False)


# ──────────────────────────────────────────────────────────────────────
# STAGE TRANSITIONS
# ──────────────────────────────────────────────────────────────────────

async def _advance(
    *,
    state: UploadFlowState,
    user_message: str,
    language: str,
    user_id_evolve: Optional[str],
    mobile_number: str,
    scanner_base_url: str,
) -> HandlerResult:

    stage = state.stage

    # ---------- After submenu, expect 1 / 2 / 3 ----------
    if stage == STAGE_SUBMENU_SHOWN:
        choice = _parse_numbered_choice(user_message)

        if choice == 1:
            return await _enter_dealer_selection(
                state=state,
                next_stage=STAGE_QR_NAME,
                language=language,
                user_id_evolve=user_id_evolve,
            )

        if choice == 2:
            return await _enter_dealer_selection(
                state=state,
                next_stage=STAGE_CLAIM_NAME,
                language=language,
                user_id_evolve=user_id_evolve,
            )

        if choice == 3:
            # Claim status flow stays on the LLM agent — the user explicitly
            # asked us not to disturb it. Clear our state and let the agent
            # take over from here.
            state.clear()
            return HandlerResult(
                handled=False,
                flow_state_json=state.to_json(),
                clear_legacy_dealer_flow_stage=True,
            )

        # Anything else → re-show submenu with a small error nudge.
        return HandlerResult(
            handled=True,
            assistant_reply=M.invalid_submenu_choice(language) + "\n\n" + M.submenu(language),
            flow_state_json=state.to_json(),
        )

    # ---------- Awaiting dealer firm name (QR or Claim) ----------
    if stage in (STAGE_QR_NAME, STAGE_CLAIM_NAME):
        query = (user_message or "").strip()
        if not query:
            return HandlerResult(
                handled=True,
                assistant_reply=M.ask_firm_name(language),
                flow_state_json=state.to_json(),
            )

        dealers = await fetch_dealers(str(user_id_evolve or "").strip())
        if dealers is None:
            return HandlerResult(
                handled=True,
                assistant_reply=M.dealer_fetch_failed(language),
                flow_state_json=state.to_json(),
            )

        if not dealers:
            return HandlerResult(
                handled=True,
                assistant_reply=M.no_dealers_found(language),
                flow_state_json=state.to_json(),
            )

        scored = search_dealers(query, dealers)
        if not scored:
            # Stay on the same stage so the user can try another spelling.
            return HandlerResult(
                handled=True,
                assistant_reply=M.no_match(language, query),
                flow_state_json=state.to_json(),
            )

        # Store the full ranked list; display starts at page 0.
        all_matches: List[Dict[str, Any]] = [
            {
                "firm_name": dealer["firm_name"],
                "dealer_code": dealer["dealer_code"],
                "city": dealer.get("city", ""),
                "branch": dealer.get("branch", ""),
            }
            for dealer, _score in scored
        ]

        state.all_matches = all_matches
        state.page = 0
        state.stage = STAGE_QR_SERIAL if stage == STAGE_QR_NAME else STAGE_CLAIM_SERIAL

        page_matches = state.current_page_matches()
        return HandlerResult(
            handled=True,
            assistant_reply=M.dealer_match_list(
                language, query, page_matches, has_more=state.has_next_page()
            ),
            flow_state_json=state.to_json(),
        )

    # ---------- Awaiting serial number (QR or Claim) ----------
    if stage in (STAGE_QR_SERIAL, STAGE_CLAIM_SERIAL):
        chosen = _parse_numbered_choice(user_message)
        page_matches = state.current_page_matches()
        # Option 11 is a stable paging command on every full dealer page.
        # Never derive it from mutable page contents.
        show_more_serial = PAGE_SIZE + 1

        # ── "Show more" selected ──────────────────────────────────
        if chosen == show_more_serial and state.has_next_page():
            state.page += 1
            next_page_matches = state.current_page_matches()
            return HandlerResult(
                handled=True,
                assistant_reply=M.dealer_match_list(
                    language, "", next_page_matches, has_more=state.has_next_page()
                ),
                flow_state_json=state.to_json(),
            )

        # ── Valid serial from current page ────────────────────────
        valid_serials = {row["serial"] for row in page_matches}
        if chosen is None or chosen not in valid_serials:
            return HandlerResult(
                handled=True,
                assistant_reply=M.invalid_serial(language, show_more=state.has_next_page()),
                flow_state_json=state.to_json(),
            )

        # Resolve display serial → actual dealer via page offset.
        actual_index = state.page * PAGE_SIZE + (chosen - 1)
        selected = state.all_matches[actual_index]
        state.selected_firm_name = selected["firm_name"]
        state.selected_dealer_code = selected["dealer_code"]

        # === QR PATH: build URL and finish ===
        if stage == STAGE_QR_SERIAL:
            url = _build_qr_url(
                scanner_base_url=scanner_base_url,
                user_id_evolve=user_id_evolve,
                mobile_number=mobile_number,
                dealer_code=selected["dealer_code"],
            )
            reply = M.qr_link_ready(language, selected["firm_name"], url)

            # Flow finished — clear state.
            state.clear()
            return HandlerResult(
                handled=True,
                assistant_reply=reply,
                flow_state_json=state.to_json(),
                clear_legacy_dealer_flow_stage=True,
                end_of_flow=True,
            )

        # === CLAIM PATH: ask for purchase amount ===
        state.stage = STAGE_CLAIM_AMOUNT
        return HandlerResult(
            handled=True,
            assistant_reply=M.ask_purchase_amount(language, selected["firm_name"]),
            flow_state_json=state.to_json(),
        )

    # ---------- Awaiting purchase amount (Claim path) ----------
    if stage == STAGE_CLAIM_AMOUNT:
        amount = _is_positive_amount(user_message)
        if amount is None:
            return HandlerResult(
                handled=True,
                assistant_reply=M.invalid_amount(language),
                flow_state_json=state.to_json(),
            )

        result = await create_claim(
            user_id_evolve=str(user_id_evolve or "").strip(),
            dealer_code=state.selected_dealer_code,
            purchase_value=amount,
        )

        server_message = result.get("message") or ""
        if result.get("ok"):
            reply = f"Claim created: {server_message}" if server_message else "Claim created successfully."
        else:
            reply = f"Claim failed: {server_message}" if server_message else "Claim creation failed."

        state.clear()
        return HandlerResult(
            handled=True,
            assistant_reply=reply,
            flow_state_json=state.to_json(),
            clear_legacy_dealer_flow_stage=True,
            end_of_flow=True,
            translate_reply=True,
        )

    # ---------- Should never happen — bail out gracefully ----------
    logger.warning("[upload_flow] unreachable stage=%r — clearing state", stage)
    state.clear()
    return HandlerResult(
        handled=False,
        flow_state_json=state.to_json(),
        clear_legacy_dealer_flow_stage=True,
    )


# ──────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────

async def _enter_dealer_selection(
    *,
    state: UploadFlowState,
    next_stage: str,
    language: str,
    user_id_evolve: Optional[str],
) -> HandlerResult:
    """
    Shared transition for both QR and Claim sub-flows: prefetch the dealer
    list (so the cache is warm when the user types the firm name) and ask
    for the firm name.
    """
    user_id = str(user_id_evolve or "").strip()
    if not user_id:
        return HandlerResult(
            handled=True,
            assistant_reply=M.dealer_fetch_failed(language),
            flow_state_json=state.to_json(),
        )

    dealers = await fetch_dealers(user_id)
    if dealers is None:
        return HandlerResult(
            handled=True,
            assistant_reply=M.dealer_fetch_failed(language),
            flow_state_json=state.to_json(),
        )

    if not dealers:
        # User has zero dealers — abort the flow cleanly.
        state.clear()
        return HandlerResult(
            handled=True,
            assistant_reply=M.no_dealers_found(language),
            flow_state_json=state.to_json(),
            clear_legacy_dealer_flow_stage=True,
            end_of_flow=True,
        )

    state.stage = next_stage
    state.all_matches = []
    state.page = 0
    state.selected_firm_name = ""
    state.selected_dealer_code = ""

    return HandlerResult(
        handled=True,
        assistant_reply=M.ask_firm_name(language),
        flow_state_json=state.to_json(),
    )


def _build_qr_url(
    *,
    scanner_base_url: str,
    user_id_evolve: Optional[str],
    mobile_number: str,
    dealer_code: str,
) -> str:
    """
    Build the QR scanner URL deterministically. The user explicitly
    requested that no LLM be involved in URL construction so dealer_code
    is never paraphrased or invented.

    Format:
      <scanner_base_url>/scanner
        ?user_id_evolve=<user_id_evolve>
        &whatsapp_number=<mobile_number>
        &dealer_code=<dealer_code>
    """
    base = (scanner_base_url or "").rstrip("/")
    if not base:
        import os
        base = os.getenv("SCANNER_BASE_URL", "").rstrip("/")

    uid = quote_plus(str(user_id_evolve or "").strip())
    mob = quote_plus(str(mobile_number or "").strip())
    code = quote_plus(str(dealer_code or "").strip())

    return f"{base}/scanner?user_id_evolve={uid}&whatsapp_number={mob}&dealer_code={code} "
