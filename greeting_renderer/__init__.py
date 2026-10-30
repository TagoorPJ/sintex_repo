"""Renders greeting templates to JPEG. The backend uses it, but it works standalone too:

    from greeting_renderer import render_greeting
    jpeg = render_greeting(template_dict, name="Vishal Verma", number="9930577843",
                           enterprise="Ankur Enterprizes")
"""
from __future__ import annotations

from pathlib import Path

from .festivals import match as match_festival
from .model import TemplateDocument, TextField, VARIABLE_KEYS
from .render import BackgroundSource, render, to_jpeg

__all__ = ["TemplateDocument", "TextField", "VARIABLE_KEYS", "load_template", "match_festival", "render_greeting"]


def load_template(source: str | Path | dict | TemplateDocument) -> TemplateDocument:
    """Takes a dict, a JSON string or a path to a .json file."""
    if isinstance(source, TemplateDocument):
        return source
    if isinstance(source, dict):
        return TemplateDocument.model_validate(source)
    if isinstance(source, str) and source.lstrip().startswith("{"):
        return TemplateDocument.model_validate_json(source)
    return TemplateDocument.model_validate_json(Path(source).read_text(encoding="utf-8"))


def render_greeting(
    template: str | Path | dict | TemplateDocument,
    values: dict[str, str | None] | None = None,
    *,
    name: str | None = None,
    number: str | None = None,
    enterprise: str | None = None,
    background: BackgroundSource = None,
) -> bytes:
    """Returns JPEG bytes, aiming for 200 KB. Only pass background (path, bytes or
    PIL image) if the template doesn't embed one."""
    doc = load_template(template)
    merged = {"name": name, "number": number, "enterprise": enterprise, **(values or {})}
    if background is None and doc.background is not None:
        background = doc.background.data_url
    image = render(doc.canvas.width, doc.canvas.height, background, doc.fields, merged)
    return to_jpeg(image)
