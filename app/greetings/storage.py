"""Local file storage for backgrounds, thumbnails, and one-time rendered greeting cards."""
from __future__ import annotations

import time
import uuid
from pathlib import Path

from .config import greeting_settings

ASSETS = "assets"
THUMBS = "thumbs"

for _sub in (ASSETS, THUMBS):
    (greeting_settings.storage_dir / _sub).mkdir(parents=True, exist_ok=True)
greeting_settings.outbox_dir.mkdir(parents=True, exist_ok=True)


_fallback_storage = Path("D:/sintex_template_feature/backend/storage")


def path_for(key: str) -> Path:
    path = (greeting_settings.storage_dir / key).resolve()
    if path.exists():
        return path
    if _fallback_storage.exists():
        fallback_path = (_fallback_storage / key).resolve()
        if fallback_path.exists():
            return fallback_path
    return path


def save(key: str, data: bytes) -> Path:
    path = path_for(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return path


def exists(key: str) -> bool:
    return path_for(key).exists()


def url_for(key: str, base_url: str = "") -> str:
    return f"{base_url}/media/{key}"


def _card_path(token: str) -> Path | None:
    try:
        return greeting_settings.outbox_dir / f"{uuid.UUID(hex=token).hex}.jpg"
    except ValueError:
        return None


def stash_card(data: bytes) -> str:
    """Holds the card until someone downloads it, returns the token."""
    token = uuid.uuid4().hex
    path = greeting_settings.outbox_dir / f"{token}.jpg"
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return token


def peek_card(token: str) -> bool:
    path = _card_path(token)
    return bool(path and path.exists())


def take_card(token: str) -> bytes | None:
    """Returns the card data. Kept until sweep_cards cleans it after TTL."""
    path = _card_path(token)
    if path is None or not path.exists():
        return None
    try:
        return path.read_bytes()
    except Exception:
        return None


def sweep_cards(max_age_seconds: int) -> int:
    """Drop cards nobody picked up in time, returns the count."""
    cutoff = time.time() - max_age_seconds
    removed = 0
    if not greeting_settings.outbox_dir.exists():
        return 0
    for path in greeting_settings.outbox_dir.iterdir():
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except FileNotFoundError:
            pass
    return removed
