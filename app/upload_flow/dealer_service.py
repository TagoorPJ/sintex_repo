"""
upload_flow/dealer_service.py

Direct (non-LLM) wrappers around the Evolve dealer + claim APIs used by the
deterministic Upload Purchase handler.

Why a separate module:
The existing find_dealer_tool / create_claim_tool are LangChain `@tool`
decorated and intended for the LLM agent. They embed extra rules (3-mode
state machine, dealer_flow_stage strings, JSON envelopes for the LLM)
that are unhelpful when calling the same APIs deterministically from
plain Python. This module gives clean, typed Python helpers and uses the
same fuzzy-match logic so behaviour is identical.
"""

from __future__ import annotations

import os
import re
import time
from typing import List, Optional, Tuple

import httpx
from rapidfuzz import fuzz
from unidecode import unidecode
from dotenv import load_dotenv

from app.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

# ──────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────
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

FETCH_LIMIT = 2000         # the user said the dealer list is ~500 dealers
PAGE_SIZE = 10             # dealers shown per page
MIN_SCORE = 0.65           # same threshold as find_dealer_tool

# In-process cache of dealer lists — keyed by user_id, TTL 30 min
CACHE_TTL_SECONDS = 1800
_DEALER_CACHE: dict = {}


# ──────────────────────────────────────────────────────────────────────
# CACHE
# ──────────────────────────────────────────────────────────────────────

def _cache_get(user_id: str):
    item = _DEALER_CACHE.get(user_id)
    if not item:
        return None
    if int(time.time()) - item["ts"] > CACHE_TTL_SECONDS:
        _DEALER_CACHE.pop(user_id, None)
        return None
    return item["data"]


def _cache_set(user_id: str, data):
    _DEALER_CACHE[user_id] = {"data": data, "ts": int(time.time())}


def clear_dealer_cache(user_id: str) -> None:
    _DEALER_CACHE.pop(str(user_id), None)


# ──────────────────────────────────────────────────────────────────────
# FUZZY MATCH
# ──────────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """
    Normalise a firm-name string for fuzzy matching.

    Steps (in order):
      1. Transliterate any non-Latin characters to ASCII via unidecode.
         This is what lets a Hindi/Marathi user type "अमिता सैनिटरी" and
         match against the English dealer name "AMITA SANITARY" stored
         in the API.
      2. Lower-case everything.
      3. Strip HTML entities like &nbsp;.
      4. Replace non-alphanumeric characters with spaces.
      5. Collapse runs of whitespace.
      6. Drop common firm-prefix tokens like "m", "ms", "m/s" that users
         often add or omit and that would otherwise distort the score.
    """
    text = unidecode(str(text or "")).lower().strip()
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
    s1 = fuzz.token_sort_ratio(q, t)
    s2 = fuzz.partial_ratio(q, t)
    s3 = fuzz.token_set_ratio(q, t)
    return max(s1, s2, s3) / 100


def search_dealers(query: str, dealers: List[dict]) -> List[Tuple[dict, float]]:
    """
    Return top-N dealers whose firm_name fuzzy-matches `query` above MIN_SCORE,
    sorted highest score first.
    """
    scored = []
    for d in dealers:
        score = _fuzzy_score(query, d["firm_name"])
        if score >= MIN_SCORE:
            scored.append((d, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


# ──────────────────────────────────────────────────────────────────────
# EVOLVE: FETCH DEALERS
# ──────────────────────────────────────────────────────────────────────

async def fetch_dealers(user_id_evolve: str, force: bool = False) -> Optional[List[dict]]:
    """
    Fetch the dealer list for a given user from the Evolve find-dealer API,
    with in-memory caching.

    Returns:
        list of {"firm_name": str, "dealer_code": str} on success,
        None on any failure (network, non-200, empty result, ...).
    """
    user_id = str(user_id_evolve).strip()
    if not user_id or user_id.lower() in ("", "none", "null", "undefined"):
        logger.error(f"[dealer_service] invalid user_id_evolve: {user_id_evolve!r}")
        return None

    if not force:
        cached = _cache_get(user_id)
        if cached:
            logger.info(f"[dealer_service] using cached dealers for user {user_id} ({len(cached)} entries)")
            return cached

    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        logger.error(f"[dealer_service] user_id_evolve not int-castable: {user_id!r}")
        return None

    if not BASE_URL:
        logger.error("[dealer_service] EVOLVE_API_URL not configured")
        return None

    url = f"{BASE_URL}/find-dealer"
    payload = {"user_id": user_id_int, "page": 1, "limit": FETCH_LIMIT}

    logger.info(f"[dealer_service] POST {url} | payload={payload}")

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=HEADERS)
    except httpx.TimeoutException:
        logger.error("[dealer_service] timeout fetching dealers")
        return None
    except Exception:
        logger.exception("[dealer_service] unexpected error fetching dealers")
        return None

    if resp.status_code != 200:
        logger.error(
            f"[dealer_service] non-200 response from find-dealer: "
            f"status={resp.status_code} body={resp.text[:300]}"
        )
        return None

    try:
        data = resp.json()
    except Exception:
        logger.exception("[dealer_service] could not parse JSON from find-dealer")
        return None

    if data.get("status") != "success":
        logger.error(f"[dealer_service] find-dealer returned non-success: {data}")
        return None

    rows = data.get("dealer_list", []) or []
    dealers: List[dict] = []
    for row in rows:
        firm = str(row.get("firm_name", "")).strip()
        code = str(row.get("dealer_code", "")).strip()
        city = str(row.get("city", "")).strip()
        branch = str(row.get("branch", "")).strip()
        if firm and code:
            dealers.append({
                "firm_name": firm,
                "dealer_code": code,
                "city": city,
                "branch": branch,
            })

    if not dealers:
        logger.warning("[dealer_service] find-dealer returned an empty dealer list")
        return None

    _cache_set(user_id, dealers)
    logger.info(f"[dealer_service] cached {len(dealers)} dealers for user {user_id}")
    return dealers


# ──────────────────────────────────────────────────────────────────────
# EVOLVE: CREATE CLAIM
# ──────────────────────────────────────────────────────────────────────

async def create_claim(
    user_id_evolve: str,
    dealer_code: str,
    purchase_value: float,
) -> dict:
    """
    Direct call to the Evolve create-claim endpoint.

    Returns a dict:
      {
        "ok": bool,
        "message": str,                 # server message or local error
        "raw": dict | None,             # raw JSON from server, when available
      }
    """
    try:
        user_id_int = int(str(user_id_evolve).strip())
    except (TypeError, ValueError):
        return {"ok": False, "message": "Invalid user id.", "raw": None}

    dealer_code = str(dealer_code).strip()
    if not dealer_code:
        return {"ok": False, "message": "Missing dealer code.", "raw": None}

    if purchase_value is None or purchase_value <= 0:
        return {"ok": False, "message": "Invalid purchase amount.", "raw": None}

    if not BASE_URL:
        return {"ok": False, "message": "Evolve API not configured.", "raw": None}

    url = f"{BASE_URL}/claim/create"
    payload = {
        "user_id": user_id_int,
        "retailerMerchantId": dealer_code,
        "purchaseValue": float(purchase_value),
    }

    logger.info(f"[dealer_service] POST {url} | payload={payload}")

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=HEADERS)
    except httpx.TimeoutException:
        logger.error("[dealer_service] timeout creating claim")
        return {"ok": False, "message": "Request timed out.", "raw": None}
    except Exception:
        logger.exception("[dealer_service] unexpected error creating claim")
        return {"ok": False, "message": "Something went wrong.", "raw": None}

    logger.info(f"[dealer_service] create-claim status={resp.status_code} body={resp.text[:400]}")

    try:
        body = resp.json()
    except Exception:
        body = None

    # Treat 200 + 201 both as success-eligible; the Evolve gateway has been
    # observed to use both. Final success is always confirmed by `status`
    # in the response body.
    if resp.status_code in (200, 201) and isinstance(body, dict) and body.get("status") == "success":
        return {
            "ok": True,
            "message": body.get("message", ""),
            "raw": body,
        }

    # Failure path — extract whatever message we can.
    server_msg = ""
    if isinstance(body, dict):
        server_msg = body.get("message") or body.get("error") or ""

    return {
        "ok": False,
        "message": server_msg,
        "raw": body if isinstance(body, dict) else None,
    }