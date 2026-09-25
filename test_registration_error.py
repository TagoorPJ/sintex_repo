"""
Standalone test script to verify registration error handling.

Tests:
1. Tool returns specific reason when Evolve reports "already registered" and validation reports "Your account has been blocked."
2. Tool returns "You are already registered" when validation finds no member ID.
3. Tool returns custom Evolve error messages (e.g. "Mobile number already exists").
4. Tool returns pincode_error when pincode is invalid.

Run with:
    python test_registration_error.py
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

from app.tools.user_info_tool import submit_user_registration
from app.utils.evolve_member_validator import MemberValidationResult


async def run_tests():
    print("=" * 60)
    print("RUNNING REGISTRATION ERROR HANDLING TESTS")
    print("=" * 60)

    payload = json.dumps(
        {
            "name": "Toyyab ali",
            "mobile_number": "916395691735",
            "pincode": "247001",
            "callback": True,
        }
    )

    # -------------------------------------------------------------
    # Test 1: Account Blocked Scenario (from logs)
    # -------------------------------------------------------------
    print("\n[Test 1] Evolve register: 'already registered' + validate: 'Your account has been blocked.'")
    with patch(
        "app.tools.user_info_tool.call_evolve_api", new_callable=AsyncMock
    ) as mock_evolve, patch(
        "app.tools.user_info_tool.validate_member_by_mobile",
        new_callable=AsyncMock,
    ) as mock_val:

        mock_evolve.return_value = {
            "status": "error",
            "message": "You are already registered",
            "member_id": "",
        }
        mock_val.return_value = MemberValidationResult(
            member_id=None,
            is_valid=False,
            message="Your account has been blocked.",
        )

        result_raw = await submit_user_registration.ainvoke({"payload": payload})
        result = json.loads(result_raw)

        print(f"  Tool result: {result}")
        assert result.get("status") == "error", f"Expected error, got {result.get('status')}"
        assert (
            result.get("message") == "Your account has been blocked."
        ), f"Expected 'Your account has been blocked.', got {result.get('message')}"
        print("  ✓ PASSED: Specific error 'Your account has been blocked.' returned to agent")

    # -------------------------------------------------------------
    # Test 2: Already Registered without validation message
    # -------------------------------------------------------------
    print("\n[Test 2] Evolve register: 'You are already registered' (no validation message)")
    with patch(
        "app.tools.user_info_tool.call_evolve_api", new_callable=AsyncMock
    ) as mock_evolve, patch(
        "app.tools.user_info_tool.validate_member_by_mobile",
        new_callable=AsyncMock,
    ) as mock_val:

        mock_evolve.return_value = {
            "status": "error",
            "message": "You are already registered",
            "member_id": "",
        }
        mock_val.return_value = MemberValidationResult(
            member_id=None, is_valid=False, message=None
        )

        result_raw = await submit_user_registration.ainvoke({"payload": payload})
        result = json.loads(result_raw)

        print(f"  Tool result: {result}")
        assert result.get("status") == "error"
        assert result.get("message") == "You are already registered"
        print("  ✓ PASSED: Specific error 'You are already registered' returned")

    # -------------------------------------------------------------
    # Test 3: Custom Evolve Error Message
    # -------------------------------------------------------------
    print("\n[Test 3] Custom error message from Evolve API")
    with patch(
        "app.tools.user_info_tool.call_evolve_api", new_callable=AsyncMock
    ) as mock_evolve:
        mock_evolve.return_value = {
            "status": "error",
            "message": "Mobile number is registered under distributor category",
        }

        result_raw = await submit_user_registration.ainvoke({"payload": payload})
        result = json.loads(result_raw)

        print(f"  Tool result: {result}")
        assert result.get("status") == "error"
        assert (
            result.get("message")
            == "Mobile number is registered under distributor category"
        )
        print("  ✓ PASSED: Custom error propagated directly to agent")

    # -------------------------------------------------------------
    # Test 4: Pincode Error
    # -------------------------------------------------------------
    print("\n[Test 4] Pincode error handling")
    with patch(
        "app.tools.user_info_tool.call_evolve_api", new_callable=AsyncMock
    ) as mock_evolve:
        mock_evolve.return_value = {
            "status": "error",
            "message": "Pincode is not serviceable",
        }

        result_raw = await submit_user_registration.ainvoke({"payload": payload})
        result = json.loads(result_raw)

        print(f"  Tool result: {result}")
        assert result.get("status") == "pincode_error"
        assert result.get("message") == "pincode_not_found"
        print("  ✓ PASSED: Pincode error handled as pincode_error")

    # -------------------------------------------------------------
    # Test 5: Successful Recovery of Existing Member ID
    # -------------------------------------------------------------
    print("\n[Test 5] Already registered with successful member recovery")
    with patch(
        "app.tools.user_info_tool.call_evolve_api", new_callable=AsyncMock
    ) as mock_evolve, patch(
        "app.tools.user_info_tool.validate_member_by_mobile",
        new_callable=AsyncMock,
    ) as mock_val, patch(
        "app.tools.user_info_tool.update_member_id_in_wati",
        new_callable=AsyncMock,
    ):

        mock_evolve.return_value = {
            "status": "error",
            "message": "You are already registered",
            "member_id": "",
        }
        mock_val.return_value = MemberValidationResult(
            member_id="MEM12345", is_valid=True, message=None
        )

        result_raw = await submit_user_registration.ainvoke({"payload": payload})
        result = json.loads(result_raw)

        print(f"  Tool result: {result}")
        assert result.get("status") == "success"
        assert result.get("user_id") == "MEM12345"
        print("  ✓ PASSED: Member ID recovered and success returned")

    print("\n" + "=" * 60)
    print("ALL REGISTRATION ERROR TESTS PASSED SUCCESSFULLY! 🎉")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_tests())
