"""
app/utils/pdf_utils.py

PDF generation helpers used by the reward statement tool.

We use fpdf2 (the PyPI package name is `fpdf2`, but the import name is
still `fpdf`). It's a lightweight, pure-Python library — no system
dependencies — which matters because this tool runs on Windows dev
machines and Linux servers alike.

Why not pandas:
The original snippet the user shared used pandas only to iterate rows.
A plain list-of-dicts loop is just as readable and saves a heavy
dependency.

PDF layout for a reward statement:

  ┌─────────────────────────────────────────────────────────┐
  │   Reward Statement                            [logo]    │
  │                                                         │
  │   Customer: <name>            Period: <from> – <to>     │
  │   Mobile  : <phone>                                     │
  │                                                         │
  │   ┌──────────┬───────────────┬────────────┬──────┬──────┐│
  │   │ Date     │ Product       │ QR Code    │ Pts  │ Stat ││
  │   ├──────────┼───────────────┼────────────┼──────┼──────┤│
  │   │ 2025-04… │ Sintex Tank…  │ QR123…     │  150 │ OK   ││
  │   │ ...      │ ...           │ ...        │  ... │ ...  ││
  │   └──────────┴───────────────┴────────────┴──────┴──────┘│
  │                                                         │
  │   Total Transactions : N                                │
  │   Total Points Earned: NNNN                             │
  └─────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import os
from typing import Iterable, List, Optional, Tuple

from fpdf import FPDF

from app.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
# Where the generated PDFs are written. Must be writable by the
# uvicorn process. Uses a relative path so it works the same on
# Windows and Linux.
OUTPUT_DIR = os.path.join("assets", "reward_statements")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Optional logo. If the file doesn't exist, the PDF is generated
# without a logo (no error). Drop a real PNG at this path to enable.
LOGO_PATH = os.path.join("static", "img", "Sintex_Image.png")


# ---------------------------------------------------------
# COLUMN LAYOUT
# ---------------------------------------------------------
# (header, key in the row dict, column width in mm, alignment)
# Total width must equal the page's usable width (A4 = 210mm minus
# left/right margins of 10mm each = 190mm).
#
# Width budget tuning notes:
#   - Date column needs ~22mm to fit "YYYY-MM-DD" at 9pt without truncation.
#   - QR Code values are often long alphanumeric strings; give them more
#     room (62mm) so most fit verbatim.
#   - Product names are usually short or empty; 50mm is plenty.
#   - Points and Status are short — keep tight to free up width.
# 22 + 50 + 62 + 22 + 34 = 190mm  ✓
_COLUMNS: List[Tuple[str, str, int, str]] = [
    ("Date",      "trans_date",     22, "C"),
    ("Product",   "product_name",   50, "L"),
    ("QR Code",   "qrcode",         62, "C"),
    ("Points",    "points_earned",  22, "R"),
    ("Status",    "status",         34, "C"),
]

ROW_HEIGHT = 7
HEADER_HEIGHT = 8

# Body text uses a slightly smaller font than the header so long QR codes
# fit horizontally without breaking the cell border.
HEADER_FONT_SIZE = 10
BODY_FONT_SIZE = 8


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------
def _safe_str(value, default: str = "") -> str:
    """fpdf2 latin-1 encoder explodes on non-latin chars; keep it ASCII-safe."""
    if value is None:
        return default
    s = str(value)
    # Replace any character fpdf's default latin-1 font can't render.
    return s.encode("latin-1", errors="replace").decode("latin-1")


def _truncate(value, max_chars: int) -> str:
    s = _safe_str(value)
    if len(s) <= max_chars:
        return s
    # Plain ASCII ellipsis — fpdf2's default helvetica is latin-1 only
    # and chokes on Unicode "…" (U+2026).
    return s[: max_chars - 3].rstrip() + "..."


def _format_cell_value(key: str, raw) -> str:
    """
    Per-column value formatting before truncation.

    - trans_date  → strip time portion ("2026-04-30 15:39:42" -> "2026-04-30")
    - points_earned → integer-formatted ("450" not "450.0")
    - everything else → string-cast
    """
    if raw is None:
        return ""

    if key == "trans_date":
        s = str(raw).strip()
        # Be lenient about the separator between date and time. Most rows
        # are "YYYY-MM-DD HH:MM:SS" but some APIs return "YYYY-MM-DDTHH:MM:SS".
        for sep in (" ", "T"):
            if sep in s:
                s = s.split(sep, 1)[0]
                break
        return s

    if key == "points_earned":
        try:
            return f"{float(raw):.0f}"
        except (TypeError, ValueError):
            return "0"

    return str(raw)


# Approximate character budget per column at 8pt body font. These are
# tuned by eye against the real column widths above so truncated text
# never overflows the cell border.
_COL_MAX_CHARS = {
    "trans_date":    11,    # "YYYY-MM-DD" = 10 chars; +1 safety
    "product_name":  28,
    "qrcode":        36,
    "points_earned":  8,
    "status":        14,
}


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
def create_reward_statement_pdf(
    *,
    customer_name: str,
    customer_phone: str,
    user_id_evolve: str,
    from_date: str,
    to_date: str,
    statement: Iterable[dict],
    total_transactions: int,
    total_points: float,
) -> Tuple[str, str]:
    """
    Generate a PDF version of the user's reward statement.

    Returns:
        (file_name, absolute_file_path)

    The caller is responsible for sending / cleaning up the file.
    """

    safe_phone = "".join(c for c in str(customer_phone) if c.isdigit()) or "user"
    file_name = f"reward_statement_{safe_phone}_{from_date}_to_{to_date}.pdf"
    rel_path = os.path.join(OUTPUT_DIR, file_name)
    abs_path = os.path.abspath(rel_path)

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()

    # ── HEADER ────────────────────────────────────────────────
    pdf.set_font("helvetica", style="B", size=16)
    pdf.cell(0, 10, _safe_str("Reward Statement"), align="C", ln=1)

    if os.path.exists(LOGO_PATH):
        try:
            # Top-right corner logo. Keep small so it doesn't overflow.
            pdf.image(LOGO_PATH, x=170, y=8, w=30)
        except Exception:
            logger.warning(
                f"[pdf_utils] Could not embed logo at {LOGO_PATH}; "
                "continuing without it"
            )

    pdf.ln(2)

    # ── METADATA BLOCK ────────────────────────────────────────
    pdf.set_font("helvetica", size=11)
    pdf.cell(0, 6, _safe_str(f"Customer Name : {customer_name or 'N/A'}"), ln=1)
    pdf.cell(0, 6, _safe_str(f"Mobile Number : {customer_phone or 'N/A'}"), ln=1)
    pdf.cell(0, 6, _safe_str(f"User ID       : {user_id_evolve or 'N/A'}"), ln=1)
    pdf.cell(0, 6, _safe_str(f"Period        : {from_date} to {to_date}"), ln=1)

    pdf.ln(4)

    # ── TABLE HEADER ──────────────────────────────────────────
    pdf.set_font("helvetica", style="B", size=HEADER_FONT_SIZE)
    pdf.set_fill_color(230, 230, 230)
    for header, _key, width, align in _COLUMNS:
        pdf.cell(
            width, HEADER_HEIGHT, _safe_str(header),
            border=1, align=align, fill=True,
        )
    pdf.ln()

    # ── TABLE BODY ────────────────────────────────────────────
    pdf.set_font("helvetica", size=BODY_FONT_SIZE)
    statement_list = list(statement) if statement else []

    if not statement_list:
        pdf.cell(
            sum(c[2] for c in _COLUMNS),
            ROW_HEIGHT * 2,
            _safe_str("No transactions found in this period."),
            border=1, align="C",
        )
        pdf.ln()
    else:
        for row in statement_list:
            for _header, key, width, align in _COLUMNS:
                # Format-then-truncate so e.g. the time is stripped from
                # the date BEFORE we decide whether truncation is needed.
                formatted = _format_cell_value(key, row.get(key, ""))
                cell_text = _truncate(formatted, _COL_MAX_CHARS.get(key, 30))
                pdf.cell(width, ROW_HEIGHT, cell_text, border=1, align=align)
            pdf.ln()

    pdf.ln(4)

    # ── SUMMARY ────────────────────────────────────────────────
    pdf.set_font("helvetica", style="B", size=11)
    pdf.cell(0, 7, _safe_str(f"Total Transactions : {total_transactions}"), ln=1)
    pdf.cell(0, 7, _safe_str(f"Total Points Earned: {total_points:.0f}"), ln=1)

    # ── SAVE ───────────────────────────────────────────────────
    pdf.output(abs_path)
    logger.info(f"[pdf_utils] Reward statement PDF written to {abs_path}")

    return file_name, abs_path