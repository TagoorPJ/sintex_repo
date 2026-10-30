"""Fetches the font files into FONTS_DIR.

    python -m greeting_renderer.download_fonts [--copy-to ../frontend/public/fonts]
"""
from __future__ import annotations

import argparse
import shutil
import urllib.request
from pathlib import Path

from .fonts import FAMILIES, FONTS_DIR


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--copy-to", type=Path, help="also copy the files here (e.g. the editor's public/fonts)")
    args = parser.parse_args()

    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    failures = 0
    for family in FAMILIES.values():
        for weight, url in family.sources.items():
            target = FONTS_DIR / family.file_name(weight)
            if not (target.exists() and target.stat().st_size > 1000):
                try:
                    with urllib.request.urlopen(url, timeout=60) as response:
                        data = response.read()
                    if not data.startswith((b"\x00\x01\x00\x00", b"OTTO", b"true")):
                        raise ValueError("not a TrueType/OpenType file")
                    target.write_bytes(data)
                    print(f"ok   {target.name} ({len(data) // 1024} KB)")
                except Exception as exc:  # noqa: BLE001
                    failures += 1
                    print(f"FAIL {target.name}: {exc} <- {url}")
                    continue
            if args.copy_to:
                args.copy_to.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, args.copy_to / target.name)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
