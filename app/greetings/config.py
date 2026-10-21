"""Settings for festive greeting template editor and rendering service."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _list(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def _resolve_dir(env_key: str, default_sub: str) -> Path:
    val = os.getenv(env_key)
    if not val:
        return (PROJECT_ROOT / default_sub).resolve()
    p = Path(val)
    return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()


@dataclass(frozen=True)
class GreetingSettings:
    # Directory for admin artwork uploads and thumbnails
    storage_dir: Path = _resolve_dir("GREETING_STORAGE_DIR", "storage")
    # Outbox for rendered one-time cards
    outbox_dir: Path = _resolve_dir("GREETING_OUTBOX_DIR", "storage/outbox")
    # Base URL for image links handed to WhatsApp / chatbot
    public_base_url: str | None = os.getenv("PUBLIC_BASE_URL") or os.getenv("SCANNER_BASE_URL") or None
    # X-Admin-Key for the template editor UI
    admin_api_key: str | None = os.getenv("ADMIN_API_KEY") or None
    # X-Service-Key for internal / chatbot API access
    service_api_key: str | None = os.getenv("SERVICE_API_KEY") or None
    cors_origins: list[str] = field(
        default_factory=lambda: _list(os.getenv("CORS_ORIGINS"), ["http://localhost:5173", "http://127.0.0.1:5173", "*"])
    )
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_MB", "15")) * 1024 * 1024
    max_render_bytes: int = int(os.getenv("RENDER_MAX_KB", "200")) * 1024
    render_ttl_seconds: int = int(os.getenv("RENDER_TTL_MINUTES", "10")) * 60


greeting_settings = GreetingSettings()
