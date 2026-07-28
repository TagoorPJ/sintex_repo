"""
Standalone smoke test for app/upload_flow/handler.py.

Mocks the dealer-fetch + create-claim HTTP calls and walks both flows
(QR and Create Claim) end-to-end across multiple turns. Each turn
asserts the expected stage transition and assistant reply shape.

Run from the project root:
    python3 test_upload_flow.py

Useful when:
- You change the message templates in app/upload_flow/messages.py
  and want to make sure the assertions still fire.
- You change the state machine in app/upload_flow/handler.py and want
  to confirm transitions still happen in the right order.
- You want a quick local sanity check that the upload flow works
  before pushing to staging.

This file does NOT depend on the database, the LLM, or the network —
all external dependencies are stubbed.
"""

from __future__ import annotations

import asyncio
import os
import sys

# ── stub app.database so import works without postgres ─────────────
import types
fake_db = types.ModuleType("app.database")
from sqlalchemy.orm import DeclarativeBase
class _Base(DeclarativeBase):
    pass
fake_db.Base = _Base
fake_db.engine = None
fake_db.AsyncSessionLocal = None
async def _get_db():
    yield None
fake_db.get_db = _get_db
sys.modules["app.database"] = fake_db

os.environ.setdefault("AZURE_OPENAI_API_KEY", "x")
os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://x.example.com")
os.environ.setdefault("AZURE_OPENAI_MODEL", "x")
os.environ.setdefault("EVOLVE_API_URL", "https://example.com/api")
os.environ.setdefault("EVOLVE_PROGRAM", "x")
os.environ.setdefault("EVOLVE_APP", "x")
os.environ.setdefault("EVOLVE_TOKEN", "x")


# ── monkey-patch dealer_service before importing handler ──────────
from app.upload_flow import dealer_service  # noqa: E402

FAKE_DEALERS = [
    {"firm_name": "RAM ENTERPRISES",       "dealer_code": "D0001"},
    {"firm_name": "RAM TRADERS",           "dealer_code": "D0002"},
    {"firm_name": "RAMA AGENCIES",         "dealer_code": "D0003"},
    {"firm_name": "SHRI RAM PIPES",        "dealer_code": "D0004"},
    {"firm_name": "SHARMA TRADERS",        "dealer_code": "D0005"},
    {"firm_name": "GUPTA HARDWARE",        "dealer_code": "D0006"},
    {"firm_name": "PATEL SANITARY",        "dealer_code": "D0007"},
    {"firm_name": "AMRIT WATER SOLUTIONS", "dealer_code": "D0008"},
    {"firm_name": "OM SALES CORPORATION",  "dealer_code": "D0009"},
    {"firm_name": "SAI ENTERPRISE",        "dealer_code": "D0010"},
]

CALLS = {"fetch_dealers": 0, "create_claim": []}

async def fake_fetch_dealers(user_id_evolve, force=False):
    CALLS["fetch_dealers"] += 1
    if str(user_id_evolve).strip() in ("", "none", "null", "undefined"):
        return None
    return list(FAKE_DEALERS)

async def fake_create_claim(user_id_evolve, dealer_code, purchase_value):
    CALLS["create_claim"].append({
        "user_id_evolve": user_id_evolve,
        "dealer_code": dealer_code,
        "purchase_value": purchase_value,
    })
    return {
        "ok": True,
        "message": f"Claim {dealer_code} amt {purchase_value} accepted",
        "raw": {"status": "success"},
    }

dealer_service.fetch_dealers = fake_fetch_dealers
dealer_service.create_claim = fake_create_claim

# ── re-bind the names already imported in handler.py ─────────────
from app.upload_flow import handler as H  # noqa: E402
H.fetch_dealers = fake_fetch_dealers
H.create_claim = fake_create_claim


# ──────────────────────────────────────────────────────────────────
# tiny driver
# ──────────────────────────────────────────────────────────────────
class Driver:
    def __init__(self, language="english", user_id="42", mobile="919999988888"):
        self.language = language
        self.user_id = user_id
        self.mobile = mobile
        self.state_json = ""
        self.last_assistant = ""

    async def turn(self, user_message, last_assistant=None):
        if last_assistant is not None:
            self.last_assistant = last_assistant
        result = await H.handle(
            user_message=user_message,
            language=self.language,
            user_id_evolve=self.user_id,
            mobile_number=self.mobile,
            raw_state_json=self.state_json,
            last_assistant_message=self.last_assistant,
            scanner_base_url="https://api.wel-wise.com/sintex_agent_uat",
            is_registered=True,
        )
        if result.flow_state_json is not None:
            self.state_json = result.flow_state_json
        if result.assistant_reply:
            self.last_assistant = result.assistant_reply
        return result


def expect(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}{(' — ' + detail) if detail else ''}")
    if not condition:
        raise AssertionError(label)


REALISTIC_MAIN_MENU = (
    "Welcome to Sintex!\n"
    "1. My Rewards\n2. Upload Purchase\n3. Find Dealer\n"
    "4. Product Help\n5. Learn & Earn\n6. Support\n7. Fun Zone"
)


# ──────────────────────────────────────────────────────────────────
# scenarios
# ──────────────────────────────────────────────────────────────────
async def scenario_qr_english():
    print("\n=== QR FLOW (english) ===")
    d = Driver(language="english")

    r = await d.turn("2", last_assistant=REALISTIC_MAIN_MENU)
    expect("submenu rendered", r.handled and "Upload Purchase" in r.assistant_reply)
    expect("stage = submenu_shown", "submenu_shown" in d.state_json)

    r = await d.turn("1")
    expect("ask firm name (QR)", "dealer firm name" in r.assistant_reply.lower())
    expect("stage = qr_awaiting_name", "qr_awaiting_name" in d.state_json)

    r = await d.turn("ram")
    expect("numbered list shown", r.handled and "1. RAM" in r.assistant_reply.upper())
    expect("stage = qr_awaiting_serial", "qr_awaiting_serial" in d.state_json)

    r = await d.turn("99")
    expect("invalid serial error", "valid serial" in r.assistant_reply.lower())
    expect("still on qr_awaiting_serial", "qr_awaiting_serial" in d.state_json)

    r = await d.turn("2")
    expect("QR link shown", "scanner?user_id_evolve=42" in r.assistant_reply)
    expect("dealer_code = D0002 (RAM TRADERS)", "dealer_code=D0002" in r.assistant_reply)
    expect("end_of_flow=True", r.end_of_flow)
    expect("state cleared", '"stage": ""' in d.state_json)


async def scenario_claim_hindi():
    print("\n=== CREATE CLAIM (hindi, devanagari digits) ===")
    d = Driver(language="hindi")

    r = await d.turn("२", last_assistant=REALISTIC_MAIN_MENU)
    expect("submenu rendered (hindi)", "खरीद अपलोड" in r.assistant_reply)

    r = await d.turn("२")
    expect("ask firm name (hindi)", "फर्म नाम" in r.assistant_reply)
    expect("stage = claim_awaiting_name", "claim_awaiting_name" in d.state_json)

    r = await d.turn("patel")
    expect("numbered list shown", "PATEL" in r.assistant_reply.upper())
    expect("stage = claim_awaiting_serial", "claim_awaiting_serial" in d.state_json)

    r = await d.turn("१")
    expect("amount asked (hindi)", "खरीद की राशि" in r.assistant_reply)
    expect("stage = claim_awaiting_amount", "claim_awaiting_amount" in d.state_json)

    r = await d.turn("abc")
    expect("invalid amount error (hindi)", "सही राशि" in r.assistant_reply)
    expect("still on claim_awaiting_amount", "claim_awaiting_amount" in d.state_json)

    r = await d.turn("1500")
    expect("claim API called", len(CALLS["create_claim"]) == 1)
    last_call = CALLS["create_claim"][-1]
    expect(f"dealer_code = D0007 (PATEL SANITARY) — got {last_call['dealer_code']}",
           last_call["dealer_code"] == "D0007")
    expect(f"amount = 1500.0 — got {last_call['purchase_value']}",
           last_call["purchase_value"] == 1500.0)
    expect(f"user_id_evolve forwarded — got {last_call['user_id_evolve']}",
           last_call["user_id_evolve"] == "42")
    expect("success message rendered (hindi)", "सफलतापूर्वक" in r.assistant_reply)
    expect("end_of_flow=True", r.end_of_flow)
    expect("state cleared", '"stage": ""' in d.state_json)


async def scenario_keyword_trigger_marathi():
    print("\n=== KEYWORD TRIGGER (marathi) ===")
    d = Driver(language="marathi")
    r = await d.turn("scan QR", last_assistant="some earlier assistant message")
    expect("submenu rendered (marathi)", "खरेदी अपलोड" in r.assistant_reply)
    expect("stage = submenu_shown", "submenu_shown" in d.state_json)


async def scenario_no_match():
    print("\n=== NO MATCH (english) ===")
    d = Driver(language="english")
    await d.turn("2", last_assistant=REALISTIC_MAIN_MENU)
    await d.turn("1")
    r = await d.turn("zzzzzzzz")
    expect("no match error", "no dealer matched" in r.assistant_reply.lower())
    expect("stage stays qr_awaiting_name", "qr_awaiting_name" in d.state_json)


async def scenario_show_more_always_option_11():
    print("\n=== DEALER PAGINATION (OPTION 11 ALWAYS WORKS) ===")
    original_fetch = H.fetch_dealers
    paged_dealers = [
        {"firm_name": f"RAM DEALER {i:02d}", "dealer_code": f"P{i:04d}"}
        for i in range(1, 26)
    ]

    async def fetch_paged_dealers(user_id_evolve, force=False):
        return list(paged_dealers)

    H.fetch_dealers = fetch_paged_dealers
    try:
        d = Driver(language="english")
        await d.turn("2", last_assistant=REALISTIC_MAIN_MENU)
        await d.turn("1")
        r = await d.turn("ram")
        expect("page 1 shows permanent option 11", "11. Show more options" in r.assistant_reply)

        r = await d.turn("11")
        expect("bare 11 advances to page 2", "RAM DEALER 11" in r.assistant_reply)
        expect("page 2 still shows option 11", "11. Show more options" in r.assistant_reply)

        r = await d.turn("option 11")
        expect("'option 11' advances to page 3", "RAM DEALER 21" in r.assistant_reply)
        expect("last page does not show option 11", "11. Show more options" not in r.assistant_reply)
    finally:
        H.fetch_dealers = original_fetch


async def scenario_cancel_mid_flow():
    print("\n=== CANCEL MID-FLOW (hinglish) ===")
    d = Driver(language="hinglish")
    await d.turn("2", last_assistant=REALISTIC_MAIN_MENU)
    r = await d.turn("cancel")
    expect("cancel acknowledged", "cancel" in r.assistant_reply.lower())
    expect("end_of_flow=True", r.end_of_flow)
    expect("state cleared", '"stage": ""' in d.state_json)


async def scenario_unregistered_user_passthrough():
    print("\n=== UNREGISTERED USER NOT INTERCEPTED ===")
    r = await H.handle(
        user_message="2",
        language="english",
        user_id_evolve=None,
        mobile_number="919999988888",
        raw_state_json="",
        last_assistant_message=REALISTIC_MAIN_MENU,
        scanner_base_url="https://api.wel-wise.com/sintex_agent_uat",
        is_registered=False,
    )
    expect("handler returns handled=False for unregistered user", not r.handled)


async def scenario_main_menu_3_passthrough():
    print("\n=== SUBMENU OPTION 3 (CLAIM STATUS) → LLM ===")
    d = Driver(language="english")
    await d.turn("upload purchase", last_assistant="anything")
    r = await d.turn("3")
    expect("handler hands off (handled=False)", not r.handled)
    expect("state cleared so LLM sees clean slate",
           '"stage": ""' in (r.flow_state_json or ""))


async def main():
    await scenario_qr_english()
    await scenario_claim_hindi()
    await scenario_keyword_trigger_marathi()
    await scenario_no_match()
    await scenario_show_more_always_option_11()
    await scenario_cancel_mid_flow()
    await scenario_unregistered_user_passthrough()
    await scenario_main_menu_3_passthrough()
    print("\n[OK] All scenarios passed.")
    print(f"     fetch_dealers calls: {CALLS['fetch_dealers']}")
    print(f"     create_claim calls : {len(CALLS['create_claim'])}")


if __name__ == "__main__":
    asyncio.run(main())
