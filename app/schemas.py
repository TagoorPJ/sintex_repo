from __future__ import annotations
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, field_validator, model_validator


# ─── Request ────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    mobile_number: str
    user_id_evolve: Optional[str] = None
    message: Optional[str] = None   # optional — user may send image only with no text
    language: Optional[str] = None
    attachment: Optional[str] = None

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("mobile_number must not be empty")
        return v

    @field_validator("message", mode="before")
    @classmethod
    def validate_message(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        return v if v else None   # empty string → None; chat.py handles substitution

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().lower()
        return v if v else None

    @model_validator(mode="after")
    def normalize_ids(self) -> "ChatRequest":
        if self.user_id_evolve is not None:
            value = self.user_id_evolve.strip().lower()

            if value in ["", "null", "none", "undefined"]:
                self.user_id_evolve = None

        return self
# ─── Response ───────────────────────────────────────────────────────────────

class TokenUsageSchema(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    conversation_id: int
    response: str
    history: List[Dict[str, Optional[Any]]]
    status: str
    token_usage: Optional[TokenUsageSchema] = None
    language_change_requested: bool = False
    target_language: Optional[str] = None
    user_id_evolve: Optional[str] = None
    user_id_evolve_present: bool = False


# ─── DB read schemas ─────────────────────────────────────────────────────────

class UserSchema(BaseModel):
    id: int
    mobile_number: str
    user_id_evolve: Optional[str] = None
    is_registered: bool = False
    name: Optional[str] = None
    registered_via_chatbot: bool = False
    registered_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationSchema(BaseModel):
    id: int
    user_id: int
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageSchema(BaseModel):
    id: int
    conversation_id: int
    sender: str
    message: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}

class QRScanRequest(BaseModel):
    user_id_evolve: int
    qrcode: str
    whatsapp_number: str
    dealer_code: Optional[str] = None  # mapped from dealer selection; sent as retailerRtCode to Evolve