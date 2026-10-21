"""Pillow renderer. Draws the fields over the background and encodes a JPEG."""
from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from .fonts import load_font, nearest_weight, resolve_family
from .layout import TextLayout, layout_text, resolve_text
from .model import TextField

DEFAULT_MAX_BYTES = 200 * 1024
_MIN_QUALITY, _MAX_QUALITY = 35, 92
_MIN_SHORT_SIDE = 480  # don't shrink past this, text gets hard to read
SHADOW_RGBA = (0, 0, 0, 30)  # Very subtle, clean shadow

BackgroundSource = Image.Image | bytes | str | Path | None


def _measure(text: str, family_id: str, weight: int, size: int) -> float:
    return load_font(family_id, weight, size).getlength(text)


def layout_field(f: TextField, text: str) -> TextLayout:
    def resolve(family_id: str, value: str) -> tuple[str, int]:
        family = resolve_family(family_id, value)
        return family.id, nearest_weight(family, f.style.font_weight)

    return layout_text(text, f, _measure, resolve)


def _hex_to_rgba(color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16), alpha


def _draw_line(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font,
    fill,
    ls_px: float,
    align: str = "center",
) -> None:
    if not ls_px:
        anchor = "ms" if align == "center" else ("rs" if align == "right" else "ls")
        draw.text(xy, text, font=font, fill=fill, anchor=anchor)
        return

    char_widths = [font.getlength(ch) for ch in text]
    total_w = sum(char_widths) + ls_px * max(0, len(text) - 1)
    orig_x, y = xy
    if align == "center":
        cur_x = orig_x - total_w / 2.0
    elif align == "right":
        cur_x = orig_x - total_w
    else:
        cur_x = orig_x

    for i, ch in enumerate(text):
        draw.text((cur_x, y), ch, font=font, fill=fill, anchor="ls")
        cur_x += char_widths[i] + ls_px


def decode_data_url(data_url: str) -> bytes:
    _, _, payload = data_url.partition(",")
    return base64.b64decode(payload)


def create_festive_gradient(width: int, height: int) -> Image.Image:
    """Generates a rich royal crimson-to-maroon festive gradient background with warm ambient golden glow."""
    base = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(base)
    top_color = (68, 8, 18)
    mid_color = (112, 14, 32)
    bot_color = (28, 3, 7)

    for y in range(height):
        t = y / float(height)
        if t < 0.45:
            factor = t / 0.45
            r = int(top_color[0] + (mid_color[0] - top_color[0]) * factor)
            g = int(top_color[1] + (mid_color[1] - top_color[1]) * factor)
            b = int(top_color[2] + (mid_color[2] - top_color[2]) * factor)
        else:
            factor = (t - 0.45) / 0.55
            r = int(mid_color[0] + (bot_color[0] - mid_color[0]) * factor)
            g = int(mid_color[1] + (bot_color[1] - mid_color[1]) * factor)
            b = int(mid_color[2] + (bot_color[2] - mid_color[2]) * factor)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    cx, cy = width // 2, int(height * 0.4)
    max_r = int(width * 0.7)
    for r in range(max_r, 0, -25):
        alpha = int(35 * (1 - r / max_r))
        glow_draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 215, 0, alpha))
    glow = glow.filter(ImageFilter.GaussianBlur(35))
    return Image.alpha_composite(base, glow)


def open_background(source: BackgroundSource, width: int, height: int) -> Image.Image:
    if source is None:
        return create_festive_gradient(width, height)
    if isinstance(source, Image.Image):
        img = source
    elif isinstance(source, bytes):
        img = Image.open(io.BytesIO(source))
    elif isinstance(source, str) and source.startswith("data:"):
        img = Image.open(io.BytesIO(decode_data_url(source)))
    else:
        img = Image.open(source)
    img = ImageOps.exif_transpose(img).convert("RGBA")
    if img.size != (width, height):
        img = img.resize((width, height), Image.Resampling.LANCZOS)
    return img


def render(
    width: int,
    height: int,
    background: BackgroundSource,
    fields: list[TextField],
    values: dict[str, str | None],
) -> Image.Image:
    canvas = open_background(background, width, height)
    text_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(text_layer)
    shadow_draw = ImageDraw.Draw(shadow_layer)
    max_shadow_blur = 0.0

    for f in fields:
        text = resolve_text(f, values)
        if text is None:
            continue
        lay = layout_field(f, text)
        font = load_font(lay.family_id, lay.weight, lay.font_size)
        ascent, descent = font.getmetrics()
        ls_px = lay.letter_spacing_px_per_em * lay.font_size
        fill = _hex_to_rgba(f.style.color)
        align = f.style.align or "center"

        for i, line in enumerate(lay.lines):
            if align == "left":
                x = float(f.box.x)
            elif align == "right":
                x = float(f.box.x + f.box.width)
            else:
                x = float(f.box.x + f.box.width / 2.0)

            line_top = f.box.y + lay.block_top + i * lay.line_height_px
            # same half-leading as CSS so lines sit where the browser puts them
            baseline = line_top + (lay.line_height_px - (ascent + descent)) / 2 + ascent
            if f.style.shadow:
                _draw_line(
                    shadow_draw,
                    (x, baseline + lay.font_size * 0.05),
                    line,
                    font,
                    SHADOW_RGBA,
                    ls_px,
                    align=align,
                )
                max_shadow_blur = max(max_shadow_blur, lay.font_size * 0.08)
            _draw_line(draw, (x, baseline), line, font, fill, ls_px, align=align)

    if max_shadow_blur:
        canvas = Image.alpha_composite(canvas, shadow_layer.filter(ImageFilter.GaussianBlur(max_shadow_blur)))
    return Image.alpha_composite(canvas, text_layer)


def _encode(img: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


def to_jpeg(image: Image.Image, max_bytes: int = DEFAULT_MAX_BYTES) -> bytes:
    """JPEG under max_bytes. Binary-searches quality first, only shrinks the image (15% at a time) if even q35 is too big."""
    rgb = image.convert("RGB")
    while True:
        best: bytes | None = None
        lo, hi = _MIN_QUALITY, _MAX_QUALITY
        while lo <= hi:
            quality = (lo + hi) // 2
            data = _encode(rgb, quality)
            if len(data) <= max_bytes:
                best, lo = data, quality + 1
            else:
                hi = quality - 1
        if best is not None:
            return best
        if min(rgb.size) * 0.85 < _MIN_SHORT_SIDE:
            return _encode(rgb, _MIN_QUALITY)  # can't shrink further, best we can do
        rgb = rgb.resize((round(rgb.width * 0.85), round(rgb.height * 0.85)), Image.Resampling.LANCZOS)
