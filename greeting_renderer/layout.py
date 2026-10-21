"""How a value gets cleaned up and fitted into its field box.

frontend/src/features/templates/model/layout.ts is a line-for-line port of this,
keep them in sync (tests in renderer/tests/test_layout.py).

1. clean the value: trim, drop emoji/control chars, collapse spaces, case, max length
2. one line at the base size, shrinking 1px at a time down to fit.minFontSize
3. still too wide and maxLines == 2: largest size where a greedy word wrap fits in 2 lines
4. otherwise truncate the last line with an ellipsis at the min size
5. box height = baseSize * lineHeight * maxLines, text block centred vertically in it
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from .model import TextField, TextStyle

MAX_LENGTH = {"name": 40, "number": 20, "enterprise": 60}
ELLIPSIS = "\u2026"

_CONTROL = re.compile(r"[\u0000-\u001F\u007F-\u009F]")
_EMOJI = re.compile("[\\U0001F000-\\U0001FAFF\\u2600-\\u27BF\\uFE0F\\u200B\\u2060]")
_SPACES = re.compile(r"\s+")
_INDIC = re.compile("[\\u0900-\\u097F\\u0A80-\\u0AFF]")

Overflow = Literal["none", "shrunk", "wrapped", "truncated"]
# measure(text, family_id, weight, size_px) gives the advance width in px, without letter spacing
Measure = Callable[[str, str, int, int], float]


def clean_text(raw: str | None) -> str:
    if not raw:
        return ""
    text = _CONTROL.sub(" ", raw)
    text = _EMOJI.sub("", text)
    return _SPACES.sub(" ", text).strip()


def to_title_camel_case(text: str | None) -> str:
    """Normalizes any text input (lower, upper, mixed) into clean Title Case / Capitalized Words.
    Preserves common acronyms and punctuation like '&', 'Pvt', 'Ltd', 'LLP', 'Co'."""
    if not text:
        return ""
    cleaned = _SPACES.sub(" ", _CONTROL.sub(" ", text)).strip()
    if not cleaned:
        return ""

    def _capitalize(match: re.Match) -> str:
        word = match.group(0)
        u = word.upper()
        if u in {"LLP", "PVT", "LTD", "CO", "AND", "CORP", "INC", "M/S"}:
            return "&" if u == "AND" else u
        return word[:1].upper() + word[1:].lower()

    return re.sub(r"[A-Za-z0-9'&]+", _capitalize, cleaned)


def apply_case(text: str, case: str) -> str:
    if case == "upper":
        return text.upper()
    if case in ("title", "camel"):
        return to_title_camel_case(text)
    return text


def truncate_chars(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rstrip()


def resolve_text(f: TextField, values: dict[str, str | None]) -> str | None:
    """Text to draw, or None if the field should be hidden."""
    if f.kind == "text":
        text = clean_text(f.text)
    else:
        raw_val = values.get(f.variable or "")
        if f.variable == "enterprise":
            text = clean_text(raw_val).upper()
        elif f.variable == "name":
            text = to_title_camel_case(raw_val)
        else:
            text = clean_text(raw_val)
        if text:
            text = truncate_chars(text, MAX_LENGTH.get(f.variable or "name", 40))
    if not text:
        if f.kind == "variable" and f.when_empty.mode == "fallback":
            text = clean_text(f.when_empty.text)
        if not text:
            return None
    return apply_case(text, f.style.text_case)


def is_indic(text: str) -> bool:
    return bool(_INDIC.search(text))


@dataclass
class TextLayout:
    font_size: int
    lines: list[str]
    line_widths: list[float]
    overflow: Overflow
    family_id: str
    weight: int
    letter_spacing_px_per_em: float  # em, forced to 0 for Indic text
    box_height: float
    block_top: float  # top of the first line, relative to the box
    line_height_px: float
    extra: dict = field(default_factory=dict)


def box_height(style: TextStyle, max_lines: int) -> float:
    return style.font_size * style.line_height * max_lines


def layout_text(
    text: str,
    f: TextField,
    measure: Measure,
    resolve_family: Callable[[str, str], tuple[str, int]],
) -> TextLayout:
    style, fit = f.style, f.fit
    family_id, weight = resolve_family(style.font_family, text)
    ls = 0.0 if is_indic(text) else style.letter_spacing
    width = f.box.width
    base = max(1, round(style.font_size))
    minimum = max(1, min(base, round(fit.min_font_size)))

    def w(s: str, size: int) -> float:
        return measure(s, family_id, weight, size) + ls * size * len(s)

    def done(size: int, lines: list[str], overflow: Overflow) -> TextLayout:
        lh = size * style.line_height
        bh = box_height(style, fit.max_lines)
        return TextLayout(
            font_size=size,
            lines=lines,
            line_widths=[w(line, size) for line in lines],
            overflow=overflow,
            family_id=family_id,
            weight=weight,
            letter_spacing_px_per_em=ls,
            box_height=bh,
            block_top=(bh - lh * len(lines)) / 2,
            line_height_px=lh,
        )

    # 1-2. one line, shrink until it fits
    for size in range(base, minimum - 1, -1):
        if w(text, size) <= width:
            return done(size, [text], "none" if size == base else "shrunk")

    # 3. try two lines
    if fit.max_lines == 2:
        for size in range(base, minimum - 1, -1):
            lines = wrap(text, size, width, w)
            if len(lines) <= 2 and all(w(line, size) <= width for line in lines):
                return done(size, lines, "wrapped")

    # 4. give up, truncate at min size
    lines = wrap(text, minimum, width, w) if fit.max_lines == 2 else [text]
    kept = lines[: fit.max_lines]
    if len(lines) > fit.max_lines:
        kept[-1] = " ".join(lines[fit.max_lines - 1 :])
    kept = [ellipsize(line, minimum, width, w) for line in kept]
    return done(minimum, kept, "truncated")


def wrap(text: str, size: int, width: float, w: Callable[[str, int], float]) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split(" "):
        candidate = f"{current} {word}" if current else word
        if current and w(candidate, size) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def ellipsize(line: str, size: int, width: float, w: Callable[[str, int], float]) -> str:
    if w(line, size) <= width:
        return line
    chars = line
    while chars and w(chars.rstrip() + ELLIPSIS, size) > width:
        chars = chars[:-1]
    return chars.rstrip() + ELLIPSIS
