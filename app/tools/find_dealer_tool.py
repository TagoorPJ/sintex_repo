from __future__ import annotations

import os
import json
import httpx
import re
import time
from dotenv import load_dotenv
from langchain.tools import tool
from rapidfuzz import fuzz

from app.utils.logger import get_logger
from app.utils.observability import timed_httpx_request

load_dotenv()
logger = get_logger(__name__)

# ==========================================================
# CONFIG
# ==========================================================
BASE_URL = os.getenv("EVOLVE_API_URL", "").rstrip("/")
PROGRAM = os.getenv("EVOLVE_PROGRAM")
APP_NAME = os.getenv("EVOLVE_APP")
AUTH_TOKEN = os.getenv("EVOLVE_TOKEN")
REQUEST_TIMEOUT = float(os.getenv("EVOLVE_TIMEOUT", "30"))

HEADERS = {
    "accept": "*/*",
    "program": PROGRAM,
    "app": APP_NAME,
    "Content-Type": "application/json",
    "Authorization": AUTH_TOKEN,
}

FETCH_LIMIT = 500
MAX_RESULTS = 10
MIN_SCORE = 0.65
CACHE_TTL_SECONDS = 1800  # 30 mins

# ==========================================================
# MEMORY CACHE
# ==========================================================
DEALER_CACHE = {}
MATCH_CACHE = {}


# ==========================================================
# HELPERS
# ==========================================================
def _json_response(status: str, message: str, data: dict = None) -> str:
    payload = {"status": status, "message": message}
    if data:
        payload.update(data)
    return json.dumps(payload, ensure_ascii=False)


def _safe_int(value):
    try:
        return int(str(value).strip())
    except Exception:
        return None


def _now():
    return int(time.time())


def _normalize(text: str) -> str:
    text = str(text).lower().strip()
    text = text.replace("&nbsp;", " ")
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = re.sub(r"\s+", " ", text)
    remove_words = {"m", "ms", "m/s"}
    words = [w for w in text.split() if w not in remove_words]
    return " ".join(words).strip()


def _fuzzy_score(query: str, target: str) -> float:
    q = _normalize(query)
    t = _normalize(target)
    if not q or not t:
        return 0.0
    score1 = fuzz.token_sort_ratio(q, t)
    score2 = fuzz.partial_ratio(q, t)
    score3 = fuzz.token_set_ratio(q, t)
    return max(score1, score2, score3) / 100


def _search_dealers(query: str, dealers: list):
    scored = []
    for dealer in dealers:
        score = _fuzzy_score(query, dealer["firm_name"])
        if score >= MIN_SCORE:
            scored.append((dealer, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:MAX_RESULTS]


def _set_cache(store: dict, key: str, value):
    store[key] = {"data": value, "ts": _now()}


def _get_cache(store: dict, key: str):
    item = store.get(key)
    if not item:
        return None
    age = _now() - item["ts"]
    if age > CACHE_TTL_SECONDS:
        store.pop(key, None)
        return None
    return item["data"]


async def _fetch_and_cache_dealers(user_id: str) -> list | None:
    """
    Internal helper: fetches dealer list from API and stores in DEALER_CACHE.
    Returns list of dealers on success, [] when Evolve succeeds with an
    empty dealer_list, and None on any failure.
    """
    user_id_int = _safe_int(user_id)
    if not user_id_int:
        return None

    url = f"{BASE_URL}/find-dealer"
    payload = {"user_id": user_id_int, "page": 1, "limit": FETCH_LIMIT}

    logger.info(f"[find_dealer_tool] Fetching dealers | payload={payload}")

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await timed_httpx_request(
                client,
                "POST",
                url,
                api_name="evolve.find_dealer",
                endpoint="/find-dealer",
                log=logger,
                json=payload,
                headers=HEADERS,
            )

        if response.status_code != 200:
            logger.error(f"[find_dealer_tool] API returned {response.status_code}")
            return None

        result = response.json()

        if result.get("status") != "success":
            logger.error(f"[find_dealer_tool] API status not success: {result}")
            return None

        rows = result.get("dealer_list", [])
        all_dealers = []

        for row in rows:
            firm = str(row.get("firm_name", "")).strip()
            code = str(row.get("dealer_code", "")).strip()
            city = str(row.get("city", "")).strip()
            branch = str(row.get("branch", "")).strip()
            if firm and code:
                all_dealers.append({
                    "firm_name": firm,
                    "dealer_code": code,
                    "city": city,
                    "branch": branch,
                })

        if not all_dealers:
            logger.warning(
                f"[find_dealer_tool] API returned success with empty dealer_list: {result}"
            )
            return []

        _set_cache(DEALER_CACHE, user_id, all_dealers)
        logger.info(f"[find_dealer_tool] Cached {len(all_dealers)} dealers for user {user_id}")
        return all_dealers

    except httpx.TimeoutException:
        logger.error("[find_dealer_tool] Timeout fetching dealers")
        return None

    except Exception:
        logger.exception("[find_dealer_tool] _fetch_and_cache_dealers error")
        return None


# ==========================================================
# TOOL
# ==========================================================
@tool("find_dealer_tool")
async def find_dealer_tool(
    user_id_evolve: str,
    search_name: str = "",
    selected_serial: str = "",
    cached_dealers: str = "",
) -> str:
    """
    Tool Name: find_dealer_tool

    Purpose:
    Helps the user search and select the correct dealer firm name,
    then returns the correct dealer_code for QR Scan or Claim flows.

    This tool works in 3 modes automatically.

    ==================================================
    MODE 1 — FETCH DEALERS (MANDATORY FIRST STEP)
    ==================================================

    Call this tool with ONLY user_id_evolve.
    Do NOT pass search_name or selected_serial.

    Example:
    find_dealer_tool(user_id_evolve="<from COLLECTED_DATA>")

    What it does:
    - Calls dealer API
    - Fetches full dealer list
    - Stores in memory cache for this user

    AFTER MODE 1 SUCCEEDS:
    ✅ dealer_flow_stage = "awaiting_dealer_name" in response
    ✅ Your ONLY job is to ask: "Please type your dealer firm name."
    ✅ Do NOT call MODE 2 until user replies with text.
    ✅ Do NOT ask for any other input.

    ==================================================
    MODE 2 — SEARCH DEALER NAME
    ==================================================

    Call ONLY after MODE 1 has been called AND user has typed a dealer name.

    Call this tool with:
    - user_id_evolve
    - search_name = dealer name typed by user (the text they sent)

    AFTER MODE 2 SUCCEEDS:
    ✅ dealer_flow_stage = "awaiting_serial_selection" in response
    ✅ Show the numbered list EXACTLY as returned in the message field.
    ✅ Ask: "Please enter the serial number of your correct dealer."
    ✅ Do NOT call MODE 3 until user replies with a number.
    ✅ Do NOT ask for dealer name again.
    ✅ The user's next reply is their serial number choice — treat it as selected_serial.

    ==================================================
    MODE 3 — SELECT SERIAL NUMBER
    ==================================================

    Call this tool with:
    - user_id_evolve
    - selected_serial = number chosen by user (their reply after seeing the list)

    AFTER MODE 3 SUCCEEDS:
    ✅ dealer_flow_stage = "dealer_selected" in response
    ✅ Use dealer_code from result for next step (QR link or create claim).

    ==================================================
    STRICT STATE MACHINE — FOLLOW EXACTLY
    ==================================================

    STATE: initial
      → Call MODE 1 (fetch dealers)
      → Move to STATE: awaiting_dealer_name

    STATE: awaiting_dealer_name
      → User sends text → that text is the dealer name
      → Call MODE 2 with search_name = that text
      → Move to STATE: awaiting_serial_selection

    STATE: awaiting_serial_selection
      → User sends a number → that number is their serial choice
      → Call MODE 3 with selected_serial = that number
      → Move to STATE: dealer_selected

    STATE: dealer_selected
      → Use dealer_code for QR link or claim

    CRITICAL: Never re-ask for dealer name when in STATE awaiting_serial_selection.
    CRITICAL: Never re-run MODE 2 when in STATE awaiting_serial_selection.
    CRITICAL: The user's response after seeing the dealer list is ALWAYS a serial number.

    ==================================================
    CORRECT FLOW (MUST FOLLOW EXACTLY)
    ==================================================

    Step 1 → find_dealer_tool(user_id_evolve=...)           [MODE 1]
    Step 2 → Ask user: "Please type your dealer firm name."
    Step 3 → find_dealer_tool(user_id_evolve=..., search_name=<user text>) [MODE 2]
    Step 4 → Show the numbered list to user
    Step 5 → Ask: "Please enter the serial number of your dealer."
    Step 6 → find_dealer_tool(user_id_evolve=..., selected_serial=<user number>) [MODE 3]
    Step 7 → Use dealer_code from result

    ==================================================
    LANGUAGE RULE
    ==================================================

    Always ask follow-up questions in user's selected language.
    """

    user_id = str(user_id_evolve).strip()

    if not user_id or user_id.lower() in ("", "none", "null", "undefined"):
        return _json_response("error", "Valid user id required.")

    # ======================================================
    # MODE 3 : SERIAL SELECT
    # ======================================================
    if selected_serial.strip():

        serial_int = _safe_int(selected_serial)

        if serial_int is None:
            return _json_response(
                "error",
                "Please enter a valid serial number.",
                {"dealer_flow_stage": "awaiting_serial_selection"}
            )

        if cached_dealers.strip():
            try:
                matches = json.loads(cached_dealers)

                # 🔥 FIX 1: if dict format (LLM modified)
                if isinstance(matches, dict) and "dealers" in matches:
                    fixed = []
                    for i, d in enumerate(matches["dealers"], start=1):
                        fixed.append({
                            "serial": i,
                            "firm_name": d.get("firm_name") or d.get("name"),
                            "dealer_code": d.get("dealer_code")
                        })
                    matches = fixed

                # 🔥 FIX 2: ensure serial exists
                elif isinstance(matches, list):
                    for i, row in enumerate(matches, start=1):
                        if "serial" not in row:
                            row["serial"] = i

            except Exception:
                matches = []
        else:
            matches = []
        if not matches:
            return _json_response(
                "error",
                "Dealer options expired. Please search dealer name again.",
                {"dealer_flow_stage": "awaiting_dealer_name"}
            )

        lookup = {row["serial"]: row for row in matches}

        if serial_int not in lookup:
            return _json_response(
                "error",
                "Invalid selection. Please choose from shown list.",
                {"dealer_flow_stage": "awaiting_serial_selection"}
            )

        selected = lookup[serial_int]

        return _json_response(
            "success",
            f"Dealer selected: {selected['firm_name']}",
            {
                "dealer_code": selected["dealer_code"],
                "firm_name": selected["firm_name"],
                "city": selected.get("city", ""),
                "branch": selected.get("branch", ""),
                "serial": serial_int,
                "dealer_flow_stage": "dealer_selected",
                # ── AGENT INSTRUCTION ──────────────────────────────────────────
                "next_action": (
                    "Dealer has been confirmed. "
                    "Use the dealer_code above for the next step (QR link or claim). "
                    "Do NOT ask for dealer name again. Do NOT call MODE 2 again."
                ),
            }
        )

    # ======================================================
    # MODE 2 : SEARCH NAME
    # ======================================================
    if search_name.strip():

        # ✅ ALWAYS get dealer list from cache
        all_dealers = _get_cache(DEALER_CACHE, user_id) or []

        # 🔥 If cache missing → refetch
        if not all_dealers:
            logger.warning(
                f"[find_dealer_tool] Cache empty for user {user_id}, refetching..."
            )
            all_dealers = await _fetch_and_cache_dealers(user_id) or []

        # ❌ still empty → fail
        if not all_dealers:
            return _json_response(
                "error",
                "Evolve returned success, but dealer_list is empty for this account.",
                {
                    "dealer_flow_stage": "awaiting_dealer_name",
                    "evolve_status": "success",
                    "dealer_list_count": 0,
                }
            )

        query = search_name.strip()
        matches_raw = _search_dealers(query, all_dealers)

        if not matches_raw:
            return _json_response(
                "error",
                f"No dealer found matching '{query}'. Please try again.",
                {"dealer_flow_stage": "awaiting_dealer_name"}
            )

        # ✅ Build serial list (fuzzy match on firm_name only; carry city/branch for display)
        matches = []
        for i, (dealer, score) in enumerate(matches_raw, start=1):
            matches.append({
                "serial": i,
                "firm_name": dealer["firm_name"],
                "dealer_code": dealer["dealer_code"],
                "city": dealer.get("city", ""),
                "branch": dealer.get("branch", ""),
            })

        lines = [f"Found matching dealers for '{query}':\n"]
        for row in matches:
            city = row.get("city", "")
            branch = row.get("branch", "")
            line = f"{row['serial']}. {row['firm_name']}"
            if city:
                line += f" | City: {city}"
            if branch:
                line += f" | Branch: {branch}"
            lines.append(line)
        lines.append("\nPlease enter the serial number of your correct dealer.")

        return _json_response(
            "success",
            "\n".join(lines),
            {
                "match_results_json": json.dumps(matches, ensure_ascii=False),
                "match_count": len(matches),
                "dealer_flow_stage": "awaiting_serial_selection"
            }
        )

    # ======================================================
    # MODE 1 : FETCH DEALERS
    # ======================================================
    all_dealers = await _fetch_and_cache_dealers(user_id)

    if all_dealers is None:
        return _json_response(
            "error",
            "Unable to fetch dealer list. Please try again.",
            {"dealer_flow_stage": "initial"}
        )

    if not all_dealers:
        return _json_response(
            "error",
            "Evolve returned success, but dealer_list is empty for this account.",
            {
                "dealer_flow_stage": "initial",
                "evolve_status": "success",
                "dealer_list_count": 0,
            }
        )

    return _json_response(
        "success",
        "Dealer list loaded successfully.",
        {
            "total_dealers": len(all_dealers),
            "dealer_flow_stage": "awaiting_dealer_name",
            # ── AGENT INSTRUCTION ──────────────────────────────────────────
            "next_action": (
                "Dealer list is now cached. "
                "Ask the user to type their dealer firm name. "
                "Do NOT call MODE 2 yet. "
                "Wait for the user to reply with text before calling MODE 2."
            ),
        }
    )
