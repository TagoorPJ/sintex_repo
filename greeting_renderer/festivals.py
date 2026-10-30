"""Festival list, plus matching free text like "happy deepavali" to one."""
from __future__ import annotations

import difflib
import re
from collections.abc import Iterable
from typing import Protocol, TypeVar


class FestivalLike(Protocol):
    id: str
    label: str
    aliases: list[str]


F = TypeVar("F", bound=FestivalLike)

# (id, label, aliases). Same list lives in the editor at src/features/templates/model/festivals.ts
SEED: list[tuple[str, str, list[str]]] = [
    ("diwali", "Diwali", ["Deepavali", "Deepawali", "Divali"]),
    ("holi", "Holi", ["Rangwali Holi", "Dhulandi"]),
    ("navratri", "Navratri", ["Navaratri", "Garba"]),
    ("dussehra", "Dussehra", ["Dasara", "Vijayadashami", "Dassehra", "Dushera", "Dashahara"]),
    ("ganesh-chaturthi", "Ganesh Chaturthi", ["Ganesh", "Ganesh Utsav", "Ganeshotsav", "Vinayaka Chaturthi", "Vinayaka Chavithi"]),
    ("pongal", "Pongal", ["Thai Pongal", "Makar Sankranti", "Sankranti", "Uttarayan", "Lohri"]),
    ("raksha-bandhan", "Raksha Bandhan", ["Rakhi"]),
    ("janmashtami", "Janmashtami", ["Krishna Janmashtami", "Gokulashtami"]),
    ("makar-sankranti", "Makar Sankranti", ["Sankranti", "Uttarayan", "Lohri"]),
    ("gudi-padwa", "Gudi Padwa", ["Ugadi"]),
    ("baisakhi", "Baisakhi", ["Vaisakhi"]),
    ("onam", "Onam", []),
    ("eid-al-fitr", "Eid al-Fitr", ["Eid", "Ramzan Eid", "Eid ul Fitr", "Ramadan Eid"]),
    ("eid-al-adha", "Eid al-Adha", ["Bakrid", "Bakri Eid", "Eid ul Adha"]),
    ("christmas", "Christmas", ["Xmas", "Merry Christmas"]),
    ("new-year", "New Year", ["Happy New Year"]),
    ("independence-day", "Independence Day", ["15 August"]),
    ("republic-day", "Republic Day", ["26 January"]),
]

_NOISE = re.compile(r"\b(happy|greeting|greetings|wishes|wish|card|festival|the|of|for|a|me|send|give)\b")


def slugify(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:64]


def _norm(text: str) -> str:
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower().replace("-", " "))
    text = _NOISE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def match(text: str, festivals: Iterable[F], loose: bool = True) -> F | None:
    """Exact id/label/alias first. If loose, also a name inside the text
    ("diwali 2026") or a near spelling ("diwaali"). Strict only allows very close spellings."""
    wanted = _norm(text)
    if not wanted:
        return None
    names: dict[str, F] = {}
    for f in festivals:
        for candidate in (f.id, f.label, *(f.aliases or [])):
            names[_norm(candidate)] = f
    if wanted in names:
        return names[wanted]
    if not loose:
        close = difflib.get_close_matches(wanted, list(names), n=1, cutoff=0.9)
        return names[close[0]] if close else None
    for key, fest in names.items():
        if key and re.search(rf"\b{re.escape(key)}\b", wanted):
            return fest
    close = difflib.get_close_matches(wanted, list(names), n=1, cutoff=0.8)
    return names[close[0]] if close else None
