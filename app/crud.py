from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Conversation, Message, ConversationStage
from app.utils.logger import get_logger

logger = get_logger(__name__)

from sqlalchemy import select
from app.models import Message


async def get_last_message(db, conversation_id: int):
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_last_assistant_message(db, conversation_id: int):
    """Return the latest bot reply, ignoring any unmatched user messages."""
    result = await db.execute(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.sender == "assistant",
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# ─── USER ────────────────────────────────────────────────────────────────────

async def get_user_by_mobile(db: AsyncSession, mobile_number: str) -> Optional[User]:
    result = await db.execute(
        select(User).where(User.mobile_number == mobile_number)
    )
    return result.scalar_one_or_none()


async def upsert_user(
    db: AsyncSession,
    mobile_number: str,
    user_id_evolve: Optional[str] = None,
    is_registered: bool = False,
) -> User:
    user = await get_user_by_mobile(db, mobile_number)

    if user:
        # A missing request value must never erase a member ID already stored
        # in our database. The chat route resolves missing IDs through Evolve's
        # mobile validation API before calling this function.
        resolved_user_id = user_id_evolve or user.user_id_evolve
        new_is_registered = bool(resolved_user_id)
        await db.execute(
            update(User)
            .where(User.id == user.id)
            .values(
                user_id_evolve=resolved_user_id,
                is_registered=new_is_registered,
            )
        )
        await db.commit()
        await db.refresh(user)

        logger.info(
            f"[USER UPSERT] user_id={user.id} user_id_evolve={user.user_id_evolve!r} "
            f"is_registered={user.is_registered}"
        )
        logger.info("User updated", extra={"user_id": user.id, "mobile": mobile_number})

    else:
        user = User(
            mobile_number=mobile_number,
            user_id_evolve=user_id_evolve,
            is_registered=True if user_id_evolve else False,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        logger.info("User created", extra={"user_id": user.id, "mobile": mobile_number})

    return user


# ─── CONVERSATION ─────────────────────────────────────────────────────────────

async def get_active_conversation(db: AsyncSession, user_id: int) -> Optional[Conversation]:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id, Conversation.status == "active")
        .order_by(Conversation.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_conversation_by_id(db: AsyncSession, conversation_id: int) -> Optional[Conversation]:
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    return result.scalar_one_or_none()


async def create_conversation(db: AsyncSession, user_id: int) -> Conversation:
    conv = Conversation(
        user_id=user_id,
        status="active",
        stage=ConversationStage.MEMBER_CHECK,
        dealer_flow_stage="",
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)

    logger.info(
        "Conversation created",
        extra={"conversation_id": conv.id, "user_id": user_id}
    )

    return conv


async def get_or_create_conversation(db: AsyncSession, user_id: int) -> Conversation:
    conv = await get_active_conversation(db, user_id)
    if not conv:
        conv = await create_conversation(db, user_id)
    return conv


async def complete_conversation(db: AsyncSession, conversation_id: int) -> None:
    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(status="completed")
    )
    await db.commit()

    logger.info(
        "Conversation completed",
        extra={"conversation_id": conversation_id}
    )


# ─── STAGE CONTROL ────────────────────────────────────────────────────────────

async def set_conversation_stage(
    db: AsyncSession,
    conversation_id: int,
    stage: ConversationStage,
) -> None:
    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(stage=stage)
    )
    await db.commit()

    logger.info(
        "Conversation stage updated",
        extra={"conversation_id": conversation_id, "stage": stage.value}
    )


# ─── DEALER FLOW STAGE ────────────────────────────────────────────────────────

async def set_dealer_flow_stage(
    db: AsyncSession,
    conversation_id: int,
    dealer_flow_stage: str,
) -> None:
    """
    Persists the current dealer selection flow stage to the DB so that
    the next HTTP turn can read it back and inject it into the agent's
    system prompt via prefill["dealer_flow_stage"].

    Possible values:
      ""                       — no active dealer flow
      "awaiting_dealer_name"   — MODE 1 done, waiting for user to type name
      "awaiting_serial_selection" — MODE 2 done, list shown, waiting for serial
      "dealer_selected"        — MODE 3 done, dealer_code confirmed
    """
    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(dealer_flow_stage=dealer_flow_stage)
    )
    await db.commit()

    logger.info(
        "Dealer flow stage updated",
        extra={"conversation_id": conversation_id, "dealer_flow_stage": dealer_flow_stage}
    )


# ─── MESSAGES ─────────────────────────────────────────────────────────────────

async def save_message(
    db: AsyncSession,
    conversation_id: int,
    user_id: int,
    sender: str,
    message: str,
) -> Message:

    msg = Message(
        conversation_id=conversation_id,
        user_id=user_id,
        sender=sender,
        message=message,
    )

    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    return msg


async def get_recent_messages(
    db: AsyncSession,
    conversation_id: int,
    limit: int = 25,
) -> List[Message]:
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    messages = result.scalars().all()
    return list(reversed(messages))


# ─── LANGUAGE ─────────────────────────────────────────────────────────────────

async def set_conversation_language(
    db: AsyncSession,
    conversation_id: int,
    language: str | None,
) -> None:
    # language=None clears the stored language so the user is re-prompted
    # (used when the user requests a mid-conversation language change).
    stored_language = language.strip().lower() if language else None
    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(language=stored_language)
    )
    await db.commit()

    logger.info(
        "Conversation language updated",
        extra={"conversation_id": conversation_id, "language": stored_language}
    )


async def set_user_is_plumber(
    db: AsyncSession,
    user_id: int,
    is_plumber: bool,
) -> None:
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(is_plumber=is_plumber)
    )
    await db.commit()
    logger.info("User is_plumber updated", extra={"user_id": user_id, "is_plumber": is_plumber})


async def get_user_by_user_id_evolve(
    db: AsyncSession,
    user_id_evolve,
) -> Optional[User]:
    result = await db.execute(
        select(User).where(
            User.user_id_evolve == str(user_id_evolve)
        )
    )
    return result.scalar_one_or_none()

async def set_match_results_json(
    db: AsyncSession,
    conversation_id: int,
    value: str | None
) -> None:
    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(match_results_json=value)
    )
    await db.commit()
    
async def get_match_results_json(
    db: AsyncSession,
    conversation_id: int
) -> Optional[str]:
    result = await db.execute(
        select(Conversation.match_results_json)
        .where(Conversation.id == conversation_id)
    )
    return result.scalar_one_or_none()
