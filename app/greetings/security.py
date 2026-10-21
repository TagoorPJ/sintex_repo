"""Authentication & security checks for festive greetings API."""
from __future__ import annotations

import hmac
from fastapi import Header, HTTPException, status

from .config import greeting_settings


def _check(expected: str | None, given: str | None, header: str) -> None:
    if expected is None:  # no key configured = open (dev mode)
        return
    if not given or not hmac.compare_digest(expected, given):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": f"Missing or invalid {header}"},
        )


def require_admin(x_admin_key: str | None = Header(default=None)) -> str:
    _check(greeting_settings.admin_api_key, x_admin_key, "X-Admin-Key")
    return "admin"


def require_service(x_service_key: str | None = Header(default=None)) -> None:
    _check(greeting_settings.service_api_key, x_service_key, "X-Service-Key")
