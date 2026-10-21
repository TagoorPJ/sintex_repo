"""Chatbot API for festival greeting cards, image rendering, and one-time download links."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models import Festival, Template
from greeting_renderer.festivals import match
from .. import storage
from ..schemas import AvailableTemplate, GreetingRequest, GreetingResponse
from ..security import require_service
from ..service import error, live_templates, public_base, render_template, template_for_festival, thumb_key

router = APIRouter(prefix="/api/greetings", tags=["chatbot"], dependencies=[Depends(require_service)])
cards_router = APIRouter(prefix="/api/cards", tags=["chatbot"])

NO_STORE = {"Cache-Control": "no-store"}

TOOL_NAME = "generate_festival_greeting"
TOOL_DESCRIPTION = (
    "Create a personalised festival greeting card image for the user, e.g. when they ask "
    "'give me a Diwali greeting'. Returns an image URL to send on WhatsApp."
)


@router.get("/templates", response_model=list[AvailableTemplate])
async def available_templates(request: Request, db: AsyncSession = Depends(get_db)):
    """Greetings available right now, for showing the user a list to pick from."""
    base = public_base(request)
    live = await live_templates(db)
    return [
        AvailableTemplate(
            template_id=t.id,
            template_name=t.name,
            festival=t.festival_id or "",
            festival_label=t.festival.label if t.festival else (t.festival_id or ""),
            aliases=(t.festival.aliases or []) if t.festival else [],
            preview_url=f"{base}{storage.url_for(thumb_key(t.background_asset_id))}" if t.background_asset_id else "",
            width=t.canvas_width,
            height=t.canvas_height,
        )
        for t in live
    ]


@router.post(
    "/render",
    response_model=GreetingResponse,
    responses={404: {"description": "festival_not_found / no_active_template"}, 200: {"content": {"image/jpeg": {}}}},
)
async def render_greeting(
    body: GreetingRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    response: str = Query(default="json", pattern="^(json|image)$", description="`image` returns the JPEG bytes directly"),
):
    live = await live_templates(db)
    labels = [t.festival.label for t in live if t.festival]

    if body.template_id:
        stmt = (
            select(Template)
            .options(joinedload(Template.festival), joinedload(Template.background))
            .where(Template.id == body.template_id)
        )
        res = await db.scalars(stmt)
        template = res.first()
        if template is None or not template.is_live:
            raise error(404, "no_active_template", "That greeting is no longer available.", available_festivals=labels)
    else:
        fest_res = await db.scalars(select(Festival))
        festival = match(body.festival or "", list(fest_res.all()))
        if festival is None:
            raise error(404, "festival_not_found", f"No festival matches {body.festival!r}.", available_festivals=labels)
        template = await template_for_festival(db, festival.id)
        if template is None or not template.is_live:
            raise error(404, "no_active_template", f"There is no {festival.label} greeting available yet.", available_festivals=labels)

    data = render_template(template, {"name": body.name, "number": body.number, "enterprise": body.enterprise})
    if response == "image":
        return Response(content=data, media_type="image/jpeg", headers=NO_STORE)

    token = storage.stash_card(data)
    return GreetingResponse(
        image_url=f"{public_base(request)}/api/cards/{token}.jpg",
        mime_type="image/jpeg",
        width=template.canvas_width,
        height=template.canvas_height,
        template_id=template.id,
        template_name=template.name,
        festival=template.festival_id or "",
        festival_label=template.festival.label if template.festival else "",
    )


@cards_router.api_route("/{token}.jpg", methods=["GET", "HEAD"], responses={200: {"content": {"image/jpeg": {}}}})
def download_card(token: str, request: Request):
    """image_url from POST /api/greetings/render. One download only, then the card is deleted."""
    if request.method == "HEAD":
        if not storage.peek_card(token):
            raise error(404, "card_gone", "This greeting card was already sent or has expired.")
        return Response(media_type="image/jpeg", headers=NO_STORE)
    data = storage.take_card(token)
    if data is None:
        raise error(404, "card_gone", "This greeting card was already sent or has expired.")
    return Response(content=data, media_type="image/jpeg", headers=NO_STORE)


@router.get("/festivals")
async def available_festivals(db: AsyncSession = Depends(get_db)):
    """Festivals with a live template right now."""
    live = await live_templates(db)
    return [
        {"id": t.festival.id, "label": t.festival.label, "aliases": t.festival.aliases or []}
        for t in live
        if t.festival
    ]


@router.get("/tool-schema")
async def tool_schema(db: AsyncSession = Depends(get_db)):
    """OpenAI-style tool definition with whatever festivals are live right now."""
    live = await live_templates(db)
    labels = [t.festival.label for t in live if t.festival]
    return {
        "type": "function",
        "function": {
            "name": TOOL_NAME,
            "description": TOOL_DESCRIPTION
            + (f" Festivals available right now: {', '.join(labels)}." if labels else ""),
            "parameters": {
                "type": "object",
                "properties": {
                    "festival": {"type": "string", "description": "Festival the user asked for, e.g. 'Diwali', 'Holi', 'Christmas', 'New Year'"},
                    "enterprise": {"type": "string", "description": "Business / firm name to print on the card (MANDATORY)"},
                    "name": {"type": "string", "description": "Name to print on the card (MANDATORY)"},
                    "number": {"type": "string", "description": "Mobile number to print on the card, exactly as it should appear"},
                },
                "required": ["festival", "enterprise", "name"],
            },
        },
    }
