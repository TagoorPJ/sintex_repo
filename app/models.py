from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer,
    String, Text, Enum as SAEnum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum
from sqlalchemy import Text  # add import if not present

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ✅ Conversation Stage Enum (UPDATED FLOW)
class ConversationStage(str, enum.Enum):
    # ⚠️ KEEP for backward compatibility (old DB rows)
    LANGUAGE_PENDING = "language_pending"
    PROFESSION_PENDING = "profession_pending"
    MEMBER_CHECK = "member_check"
    REGISTRATION_FLOW = "registration_flow"
    NORMAL = "normal"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    mobile_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    user_id_evolve: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_registered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_plumber: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="user", cascade="all, delete-orphan"
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[str] = mapped_column(
        SAEnum("active", "completed", name="conversation_status"),
        default="active",
        nullable=False,
    )

    # ✅ Language now comes directly from payload
    language: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True
    )

    # ✅ Tracks where user is in the dealer selection flow across HTTP turns.
    # Values: "" | "awaiting_dealer_name" | "awaiting_serial_selection" | "dealer_selected"
    dealer_flow_stage: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        default="",
    )
    match_results_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # ✅ UPDATED DEFAULT STAGE (CRITICAL CHANGE)
    stage: Mapped[ConversationStage] = mapped_column(
        SAEnum(
            ConversationStage,
            name="conversation_stage_enum",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        default=ConversationStage.MEMBER_CHECK,
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="conversations")

    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    sender: Mapped[str] = mapped_column(
        SAEnum("user", "assistant", "tool", name="message_sender"),
        nullable=False,
    )

    message: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages"
    )