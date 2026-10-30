from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models import Festival, Template
from ..schemas import ActiveUpdate, TemplateCreate, TemplateOut, TemplateUpdate, TestRenderRequest, validate_fields
from ..security import require_admin
from ..service import claim_festival, error, get_asset, get_template, render_template, template_out

router = APIRouter(prefix="/api/templates", tags=["templates (admin)"], dependencies=[Depends(require_admin)])


async def _check_festival(db: AsyncSession, festival_id: str | None) -> None:
    if festival_id is not None:
        fest = await db.get(Festival, festival_id)
        if fest is None:
            raise error(422, "festival_not_found", f"Unknown festival {festival_id!r}.")


def _dump_fields(fields, width: int, height: int) -> list[dict]:
    try:
        validate_fields(fields, width, height)
    except ValueError as exc:
        raise error(422, "invalid_fields", str(exc)) from exc
    return [f.model_dump(by_alias=True) for f in fields]


@router.get("", response_model=list[TemplateOut], response_model_by_alias=True)
async def list_templates(
    db: AsyncSession = Depends(get_db),
    festival: str | None = None,
    status_: str | None = Query(default=None, alias="status", pattern="^(live|draft|inactive)$"),
    q: str | None = None,
):
    stmt = (
        select(Template)
        .options(joinedload(Template.festival), joinedload(Template.background))
        .order_by(Template.updated_at.desc())
    )
    if festival:
        stmt = stmt.where(Template.festival_id == festival)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.outerjoin(Festival).where(or_(Template.name.ilike(like), Festival.label.ilike(like)))
    res = await db.scalars(stmt)
    out = [template_out(t) for t in res.unique()]
    return [t for t in out if t.status == status_] if status_ else out


@router.post("", response_model=TemplateOut, response_model_by_alias=True, status_code=201)
async def create_template(
    body: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    x_admin_user: str | None = Header(default=None),
):
    await _check_festival(db, body.festival_id)
    if body.active:
        await claim_festival(db, body.festival_id, None, body.replace_festival)
    asset = await get_asset(db, body.background_asset_id)
    width = body.canvas.width if body.canvas else asset.width if asset else 1080
    height = body.canvas.height if body.canvas else asset.height if asset else 1620
    t = Template(
        name=body.name.strip(),
        festival_id=body.festival_id,
        is_active=body.active,
        canvas_width=width,
        canvas_height=height,
        background_asset_id=asset.id if asset else None,
        fields=_dump_fields(body.fields, width, height),
        updated_by=x_admin_user,
    )
    db.add(t)
    await db.commit()
    saved = await get_template(db, t.id)
    return template_out(saved)


@router.get("/{template_id}", response_model=TemplateOut, response_model_by_alias=True)
async def read_template(template_id: str, db: AsyncSession = Depends(get_db)):
    t = await get_template(db, template_id)
    return template_out(t)


@router.put("/{template_id}", response_model=TemplateOut, response_model_by_alias=True)
async def update_template(
    template_id: str,
    body: TemplateUpdate,
    db: AsyncSession = Depends(get_db),
    x_admin_user: str | None = Header(default=None),
):
    t = await get_template(db, template_id)
    if body.version != t.version:
        raise error(
            status.HTTP_409_CONFLICT,
            "version_conflict",
            "Someone else updated this template.",
            current=template_out(t).model_dump(by_alias=True, mode="json"),
        )
    await _check_festival(db, body.festival_id)
    active = t.is_active if body.active is None else body.active
    if active:
        await claim_festival(db, body.festival_id, t.id, body.replace_festival)
    asset = await get_asset(db, body.background_asset_id)
    t.is_active = active
    t.name = body.name.strip()
    t.festival_id = body.festival_id
    t.canvas_width, t.canvas_height = body.canvas.width, body.canvas.height
    t.background_asset_id = asset.id if asset else None
    t.fields = _dump_fields(body.fields, body.canvas.width, body.canvas.height)
    t.version += 1
    t.updated_by = x_admin_user
    t.updated_at = datetime.now(timezone.utc)
    await db.commit()
    updated = await get_template(db, t.id)
    return template_out(updated)


@router.delete("/{template_id}", status_code=204)
async def delete_template(template_id: str, db: AsyncSession = Depends(get_db)):
    t = await get_template(db, template_id)
    await db.delete(t)
    await db.commit()
    return Response(status_code=204)


@router.post("/{template_id}/duplicate", response_model=TemplateOut, response_model_by_alias=True, status_code=201)
async def duplicate_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    x_admin_user: str | None = Header(default=None),
):
    src = await get_template(db, template_id)
    copy = Template(
        name=f"Copy of {src.name}"[:80],
        festival_id=src.festival_id,
        is_active=False,
        canvas_width=src.canvas_width,
        canvas_height=src.canvas_height,
        background_asset_id=src.background_asset_id,
        fields=[{**f, "id": uuid.uuid4().hex[:12]} for f in (src.fields or [])],
        updated_by=x_admin_user,
    )
    db.add(copy)
    await db.commit()
    saved = await get_template(db, copy.id)
    return template_out(saved)


@router.put("/{template_id}/active", response_model=TemplateOut, response_model_by_alias=True)
async def set_active(template_id: str, body: ActiveUpdate, db: AsyncSession = Depends(get_db)):
    t = await get_template(db, template_id)
    if body.active and not t.is_active:
        await claim_festival(db, t.festival_id, t.id, body.replace_festival)
    t.is_active = body.active
    await db.commit()
    updated = await get_template(db, t.id)
    return template_out(updated)


@router.post("/{template_id}/render")
async def test_render(template_id: str, body: TestRenderRequest, db: AsyncSession = Depends(get_db)):
    t = await get_template(db, template_id)
    values = body.values.model_dump()
    data = render_template(t, values)
    return {
        "imageUrl": f"data:image/jpeg;base64,{base64.b64encode(data).decode()}",
        "bytes": len(data),
        "width": t.canvas_width,
        "height": t.canvas_height,
        "version": t.version,
        "chatbotRequest": {"festival": t.festival.label if t.festival else None, **values},
    }
