"""Template JSON as the editor saves and exports it."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

# the three values a WhatsApp user fills in. Admins can add static text
# elements but not new variables
VariableKey = Literal["name", "number", "enterprise"]
VARIABLE_KEYS: tuple[str, ...] = ("name", "number", "enterprise")
TemplateStatus = Literal["draft", "active", "inactive"]

MAX_TEXT_ELEMENTS = 10
FORMAT = "greeting-template"
FORMAT_VERSION = 1
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Box(CamelModel):
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)


class TextStyle(CamelModel):
    font_family: str = "poppins"
    font_weight: Literal[400, 500, 600, 700] = 700
    font_size: float = Field(default=56, ge=8, le=600)
    color: str = "#1F1F1F"
    align: Literal["left", "center", "right"] = "center"
    letter_spacing: float = Field(default=0, ge=-0.1, le=0.5)  # em
    line_height: float = Field(default=1.2, ge=0.8, le=2.5)
    text_case: Literal["none", "title", "upper"] = "none"
    shadow: bool = False

    @field_validator("color")
    @classmethod
    def _hex(cls, value: str) -> str:
        if not _HEX_COLOR.match(value):
            raise ValueError("color must be #RRGGBB")
        return value.upper()


class Fit(CamelModel):
    min_font_size: float = Field(default=32, ge=8, le=600)
    max_lines: Literal[1, 2] = 1


class WhenEmpty(CamelModel):
    mode: Literal["hide", "fallback"] = "hide"
    text: str = Field(default="", max_length=80)


class TextField(CamelModel):
    id: str = Field(min_length=1, max_length=40)
    kind: Literal["variable", "text"]
    variable: VariableKey | None = None  # kind == "variable"
    text: str | None = Field(default=None, max_length=200)  # kind == "text", typed in by the admin
    label: str | None = Field(default=None, max_length=40)  # what the admin calls this text element
    box: Box
    style: TextStyle = TextStyle()
    fit: Fit = Fit()
    when_empty: WhenEmpty = WhenEmpty()

    @model_validator(mode="after")
    def _kind_matches(self) -> "TextField":
        if self.kind == "variable" and self.variable is None:
            raise ValueError("variable fields need `variable`")
        if self.kind == "text":
            self.variable = None
            if not (self.text or "").strip():
                raise ValueError("text elements need `text`")
        if self.fit.min_font_size > self.style.font_size:
            self.fit.min_font_size = self.style.font_size
        return self


def validate_fields(fields: list[TextField], width: int, height: int) -> list[TextField]:
    seen: set[str] = set()
    ids: set[str] = set()
    text_count = 0
    for f in fields:
        if f.id in ids:
            raise ValueError(f"duplicate field id {f.id!r}")
        ids.add(f.id)
        if f.kind == "variable":
            if f.variable in seen:
                raise ValueError(f"variable {f.variable!r} is placed more than once")
            seen.add(f.variable)  # type: ignore[arg-type]
        else:
            text_count += 1
        if f.box.x + f.box.width > width + 0.5 or f.box.y > height:
            raise ValueError(f"field {f.id!r} is outside the canvas")
    if text_count > MAX_TEXT_ELEMENTS:
        raise ValueError(f"at most {MAX_TEXT_ELEMENTS} custom text elements")
    return fields


class Canvas(CamelModel):
    width: int = Field(ge=64, le=4096)
    height: int = Field(ge=64, le=4096)


class FestivalRef(CamelModel):
    id: str
    label: str
    aliases: list[str] = []


class BackgroundRef(CamelModel):
    file_name: str = "background"
    mime_type: str = "image/jpeg"
    width: int
    height: int
    data_url: str | None = None  # only set in exported files


class TemplateDocument(CamelModel):
    """An exported template (.json from the editor), background embedded."""

    format: Literal["greeting-template"] = FORMAT
    format_version: int = FORMAT_VERSION
    id: str
    name: str
    status: TemplateStatus = "draft"
    festival: FestivalRef | None = None
    canvas: Canvas
    background: BackgroundRef | None = None
    fields: list[TextField] = []
    updated_at: str | None = None

    @model_validator(mode="after")
    def _valid_fields(self) -> "TemplateDocument":
        validate_fields(self.fields, self.canvas.width, self.canvas.height)
        return self
