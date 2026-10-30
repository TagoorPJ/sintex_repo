"""Schemas for Greeting Template Studio Admin API and Chatbot Greetings API."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from greeting_renderer.model import Canvas, CamelModel, TextField, validate_fields  # noqa: F401
from pydantic import BaseModel, Field, model_validator

TemplateStatus = Literal["live", "draft", "inactive"]


class AssetOut(CamelModel):
    id: str
    url: str
    thumbnail_url: str
    file_name: str
    mime_type: str
    bytes: int
    width: int
    height: int


class TemplateOut(CamelModel):
    id: str
    name: str
    festival_id: str | None
    festival_label: str | None
    status: TemplateStatus
    active: bool
    version: int
    canvas: Canvas
    background: AssetOut | None
    fields: list[TextField]
    created_at: datetime
    updated_at: datetime
    updated_by: str | None


class TemplateCreate(CamelModel):
    name: str = Field(default="Untitled template", min_length=1, max_length=80)
    festival_id: str | None = None
    canvas: Canvas | None = None
    background_asset_id: str | None = None
    fields: list[TextField] = []
    active: bool = True
    replace_festival: bool = False


class TemplateUpdate(CamelModel):
    version: int
    name: str = Field(min_length=1, max_length=80)
    festival_id: str | None
    canvas: Canvas
    background_asset_id: str | None
    fields: list[TextField]
    active: bool | None = None
    replace_festival: bool = False


class ActiveUpdate(CamelModel):
    active: bool
    replace_festival: bool = False


class FestivalOut(CamelModel):
    id: str
    label: str
    aliases: list[str]
    next_date: str | None
    active_template_id: str | None = None


class FestivalCreate(CamelModel):
    label: str = Field(min_length=2, max_length=60)
    aliases: list[str] = []
    next_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class PreviewValues(CamelModel):
    name: str | None = None
    number: str | None = None
    enterprise: str | None = None


class TestRenderRequest(CamelModel):
    values: PreviewValues = PreviewValues()


# Chatbot / WhatsApp Greetings Request & Response schemas


class GreetingRequest(BaseModel):
    """Chatbot request: either festival string or template_id, plus user details."""

    festival: str | None = Field(default=None, min_length=2, max_length=60, description="Festival name, e.g. 'Diwali'")
    template_id: str | None = Field(default=None, max_length=32, description="A template_id from GET /api/greetings/templates")
    name: str | None = Field(default=None, max_length=120, description="Recipient's name")
    number: str | None = Field(default=None, max_length=40, description="Recipient's mobile number")
    enterprise: str | None = Field(default=None, max_length=160, description="Recipient's business or enterprise name")

    @model_validator(mode="after")
    def _festival_or_template(self) -> "GreetingRequest":
        if not self.festival and not self.template_id:
            raise ValueError("Send `festival` or `template_id`.")
        return self


class AvailableTemplate(BaseModel):
    template_id: str
    template_name: str
    festival: str
    festival_label: str
    aliases: list[str]
    preview_url: str
    width: int
    height: int


class GreetingResponse(BaseModel):
    image_url: str
    mime_type: str
    width: int
    height: int
    template_id: str
    template_name: str
    festival: str
    festival_label: str


class ErrorBody(BaseModel):
    code: str
    message: str
    available_festivals: list[str] | None = None
