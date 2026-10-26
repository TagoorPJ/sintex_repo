"""Font registry, shared with the editor.

The editor loads the same TTF files (frontend/public/fonts) so text measures the
same in the browser as it does here. OFL Google Fonts only.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont, features

_default_local_fonts = Path(__file__).resolve().parent / "fonts"
_frontend_public_fonts = Path(__file__).resolve().parent.parent / "frontend" / "public" / "fonts"
_fallback_template_fonts = Path("D:/sintex_template_feature/renderer/greeting_renderer/fonts")

# Auto-populate local fonts from frontend/public/fonts if missing
if not (_default_local_fonts.exists() and any(_default_local_fonts.glob("*.ttf"))):
    if _frontend_public_fonts.exists() and any(_frontend_public_fonts.glob("*.ttf")):
        try:
            _default_local_fonts.mkdir(parents=True, exist_ok=True)
            import shutil
            for font_file in _frontend_public_fonts.glob("*.ttf"):
                shutil.copy2(font_file, _default_local_fonts / font_file.name)
        except Exception:
            pass

_fonts_dir_env = os.getenv("GREETING_FONTS_DIR")
if _fonts_dir_env and Path(_fonts_dir_env).exists() and any(Path(_fonts_dir_env).glob("*.ttf")):
    FONTS_DIR = Path(_fonts_dir_env)
elif _default_local_fonts.exists() and any(_default_local_fonts.glob("*.ttf")):
    FONTS_DIR = _default_local_fonts
elif _frontend_public_fonts.exists() and any(_frontend_public_fonts.glob("*.ttf")):
    FONTS_DIR = _frontend_public_fonts
elif _fallback_template_fonts.exists():
    FONTS_DIR = _fallback_template_fonts
else:
    FONTS_DIR = _frontend_public_fonts

_GF = "https://raw.githubusercontent.com/google/fonts/main/ofl"
_FS = "https://cdn.jsdelivr.net/fontsource/fonts"


@dataclass(frozen=True)
class FontFamily:
    id: str
    label: str
    category: str
    sources: dict[int, str]  # weight: download url
    hint: str = ""
    selectable: bool = True  # script fallbacks aren't offered in the picker

    def file_name(self, weight: int) -> str:
        return f"{self.id}-{weight}.ttf"

    @property
    def weights(self) -> list[int]:
        return sorted(self.sources)


FAMILIES: dict[str, FontFamily] = {
    f.id: f
    for f in [
        FontFamily(
            "poppins", "Poppins", "Sans serif",
            {w: f"{_GF}/poppins/Poppins-{n}.ttf" for w, n in [(400, "Regular"), (500, "Medium"), (600, "SemiBold"), (700, "Bold")]},
        ),
        FontFamily("inter", "Inter", "Sans serif", {w: f"{_FS}/inter@latest/latin-{w}-normal.ttf" for w in (400, 500, 600, 700)}),
        FontFamily(
            "mukta", "Mukta", "Sans serif · Hindi",
            {w: f"{_GF}/mukta/Mukta-{n}.ttf" for w, n in [(400, "Regular"), (500, "Medium"), (600, "SemiBold"), (700, "Bold")]},
            hint="Latin + Devanagari",
        ),
        FontFamily("playfair", "Playfair Display", "Serif", {w: f"{_FS}/playfair-display@latest/latin-{w}-normal.ttf" for w in (400, 600, 700)}),
        FontFamily("cinzel", "Cinzel", "Display serif", {w: f"{_FS}/cinzel@latest/latin-{w}-normal.ttf" for w in (400, 600, 700)}),
        FontFamily("greatvibes", "Great Vibes", "Script", {400: f"{_GF}/greatvibes/GreatVibes-Regular.ttf"}, hint="Best for names"),
        FontFamily(
            "muktavaani", "Mukta Vaani", "Gujarati fallback",
            {w: f"{_GF}/muktavaani/MuktaVaani-{n}.ttf" for w, n in [(400, "Regular"), (500, "Medium"), (600, "SemiBold"), (700, "Bold")]},
            selectable=False,
        ),
    ]
}

DEFAULT_FAMILY = "poppins"

_DEVANAGARI = re.compile("[\\u0900-\\u097F]")
_GUJARATI = re.compile("[\\u0A80-\\u0AFF]")


def resolve_family(family_id: str, text: str) -> FontFamily:
    """Latin display fonts have no Indic glyphs, so Devanagari/Gujarati text
    switches to a Mukta font. The editor does the same in layoutText.ts."""
    if _GUJARATI.search(text):
        return FAMILIES["muktavaani"]
    if _DEVANAGARI.search(text):
        return FAMILIES["mukta"]
    return FAMILIES.get(family_id) or FAMILIES[DEFAULT_FAMILY]


def nearest_weight(family: FontFamily, weight: int) -> int:
    return min(family.weights, key=lambda w: (abs(w - weight), -w))


@lru_cache(maxsize=512)
def load_font(family_id: str, weight: int, size_px: int) -> ImageFont.FreeTypeFont:
    family = FAMILIES.get(family_id) or FAMILIES[DEFAULT_FAMILY]
    resolved_weight = nearest_weight(family, weight)
    file_name = family.file_name(resolved_weight)
    path = FONTS_DIR / file_name

    if not path.exists():
        if _frontend_public_fonts.exists() and (_frontend_public_fonts / file_name).exists():
            path = _frontend_public_fonts / file_name
        elif _default_local_fonts.exists() and (_default_local_fonts / file_name).exists():
            path = _default_local_fonts / file_name
        else:
            fallback_fam = FAMILIES[DEFAULT_FAMILY]
            fallback_file = fallback_fam.file_name(nearest_weight(fallback_fam, weight))
            if (FONTS_DIR / fallback_file).exists():
                path = FONTS_DIR / fallback_file
            elif (_frontend_public_fonts / fallback_file).exists():
                path = _frontend_public_fonts / fallback_file
            else:
                raise FileNotFoundError(f"Font file missing: {path}. Run `python -m greeting_renderer.download_fonts` or set GREETING_FONTS_DIR.")

    layout = ImageFont.Layout.RAQM if features.check("raqm") else ImageFont.Layout.BASIC
    return ImageFont.truetype(str(path), size=max(1, size_px), layout_engine=layout)


def manifest(base_url: str = "") -> list[dict]:
    return [
        {
            "id": f.id,
            "label": f.label,
            "category": f.category,
            "hint": f.hint,
            "selectable": f.selectable,
            "weights": f.weights,
            "files": {str(w): f"{base_url}/fonts/{f.file_name(w)}" for w in f.weights},
        }
        for f in FAMILIES.values()
    ]
