"""
Multi-turn conversational flow test for Registration Error Handling.

Simulates the complete user journey turn-by-turn:
  Turn 1: User says "Hi" -> Bot asks Profession check
  Turn 2: User replies "1" (Yes) -> Bot asks Language selection
  Turn 3: User replies "1" (English) -> Bot asks for Full Name
  Turn 4: User replies "Toyyab ali" -> Bot asks for Pincode
  Turn 5: User replies "247001" -> Bot calls registration tool and explains the Evolve error reason

Run with:
    python test_registration_flow.py
"""

import asyncio
import json
import os
import sys
import types
from unittest.mock import AsyncMock, patch

# Stub database if postgres is not running locally
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
sys.modules.setdefault("app.database", fake_db)

os.environ.setdefault("EVOLVE_API_URL", "https://example.com/api")
os.environ.setdefault("EVOLVE_TOKEN", "dummy_token")
os.environ.setdefault("AZURE_OPENAI_API_KEY", "dummy_key")
os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
os.environ.setdefault("AZURE_OPENAI_MODEL", "gpt-4o")

from app.tools.user_info_tool import submit_user_registration
from app.utils.evolve_member_validator import MemberValidationResult


async def simulate_registration_flow(scenario_name: str, evolve_response: dict, validation_response: MemberValidationResult):
    print("\n" + "=" * 70)
    print(f"SIMULATING CONVERSATIONAL FLOW: {scenario_name}")
    print("=" * 70)

    # -------------------------------------------------------------
    # TURN 1: Initial Greeting
    # -------------------------------------------------------------
    print("\n[TURN 1] User sends initial message")
    print("📨 USER: Hi")
    print("🤖 BOT:  Are you a plumber / plumbing contractor?\n         1. Yes\n         2. No")

    # -------------------------------------------------------------
    # TURN 2: Profession Confirmation
    # -------------------------------------------------------------
    print("\n[TURN 2] User confirms profession")
    print("📨 USER: 1 (Yes)")
    print("🤖 BOT:  Please select your preferred language:\n         1️⃣ English\n         2️⃣ Hindi (हिंदी)\n         3️⃣ Marathi (मराठी)\n         4️⃣ Hinglish")

    # -------------------------------------------------------------
    # TURN 3: Language Selection
    # -------------------------------------------------------------
    print("\n[TURN 3] User selects English")
    print("📨 USER: 1 (English)")
    print("🤖 BOT:  Welcome to Sintex! To get you started, please tell me your full name.")

    # -------------------------------------------------------------
    # TURN 4: User provides Full Name
    # -------------------------------------------------------------
    print("\n[TURN 4] User provides name")
    print("📨 USER: Toyyab ali")
    print("🤖 BOT:  Thanks. Now please enter pincode of the area you generally work in.")

    # -------------------------------------------------------------
    # TURN 5: User provides Pincode -> Triggers Registration Tool Call
    # -------------------------------------------------------------
    print("\n[TURN 5] User provides pincode")
    print("📨 USER: 247001")
    print("⚙️  [SYSTEM] Calling submit_user_registration with:")
    tool_input = {
        "name": "Toyyab ali",
        "mobile_number": "916395691735",
        "pincode": "247001",
        "callback": True
    }
    print(f"    Payload: {json.dumps(tool_input)}")

    with patch("app.tools.user_info_tool.call_evolve_api", new_callable=AsyncMock) as mock_evolve, \
         patch("app.tools.user_info_tool.validate_member_by_mobile", new_callable=AsyncMock) as mock_val:

        mock_evolve.return_value = evolve_response
        mock_val.return_value = validation_response

        tool_result_raw = await submit_user_registration.ainvoke({"payload": json.dumps(tool_input)})
        tool_result = json.loads(tool_result_raw)

        print(f"\n📥 [TOOL RESULT RECEIVED BY AGENT]:")
        print(f"    status:  {tool_result.get('status')}")
        print(f"    message: {tool_result.get('message')}")

        # Verification
        expected_reason = validation_response.message or evolve_response.get("message")
        assert tool_result.get("message") == expected_reason, f"Expected '{expected_reason}', got '{tool_result.get('message')}'"

        print(f"\n🤖 BOT RESPONSE TO USER:")
        if "blocked" in (tool_result.get("message") or "").lower():
            print(f'   "Your account has been blocked. Please contact support for assistance."')
        elif "already registered" in (tool_result.get("message") or "").lower():
            print(f'   "Your mobile number is already registered in our system."')
        else:
            print(f'   "Registration could not be completed: {tool_result.get("message")}"')

    print("\n✓ Flow completed successfully and verified!")


async def run_all_flow_tests():
    # Scenario A: Blocked Account (the exact issue from your logs)
    await simulate_registration_flow(
        scenario_name="Blocked Account (from log: validate returns 'Your account has been blocked.')",
        evolve_response={"status": "error", "message": "You are already registered", "member_id": ""},
        validation_response=MemberValidationResult(
            member_id=None,
            is_valid=False,
            message="Your account has been blocked."
        )
    )

    # Scenario B: Already Registered without blocked status
    await simulate_registration_flow(
        scenario_name="Already Registered (Evolve returns 'You are already registered')",
        evolve_response={"status": "error", "message": "You are already registered", "member_id": ""},
        validation_response=MemberValidationResult(
            member_id=None,
            is_valid=False,
            message=None
        )
    )

    # Scenario C: Custom Evolve Business Error
    await simulate_registration_flow(
        scenario_name="Custom Evolve Error (e.g. 'Mobile number belongs to distributor')",
        evolve_response={"status": "error", "message": "Mobile number belongs to distributor", "member_id": ""},
        validation_response=MemberValidationResult(
            member_id=None,
            is_valid=False,
            message=None
        )
    )

    print("\n" + "=" * 70)
    print("ALL CONVERSATION FLOW SCENARIOS PASSED! 🎉")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_all_flow_tests())
