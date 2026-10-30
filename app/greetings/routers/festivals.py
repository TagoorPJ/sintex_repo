from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models import Festival, Template
from greeting_renderer.festivals import match, slugify
from ..schemas import FestivalCreate, FestivalOut
from ..security import require_admin
from ..service import error

router = APIRouter(prefix="/api/festivals", tags=["festivals (admin)"], dependencies=[Depends(require_admin)])


async def _out(db: AsyncSession) -> list[FestivalOut]:
    stmt = (
        select(Template)
        .options(joinedload(Template.festival), joinedload(Template.background))
        .where(Template.festival_id.is_not(None))
    )
    tmpl_res = await db.scalars(stmt)
    active = {t.festival_id: t.id for t in tmpl_res.unique() if t.is_live}

    fest_res = await db.scalars(select(Festival).order_by(Festival.sort_order, Festival.label))
    return [
        FestivalOut(id=f.id, label=f.label, aliases=f.aliases or [], next_date=f.next_date, active_template_id=active.get(f.id))
        for f in fest_res.all()
    ]


@router.get("", response_model=list[FestivalOut], response_model_by_alias=True)
async def list_festivals(db: AsyncSession = Depends(get_db)):
    return await _out(db)


@router.post("", response_model=FestivalOut, response_model_by_alias=True, status_code=201)
async def create_festival(body: FestivalCreate, db: AsyncSession = Depends(get_db)):
    label = " ".join(body.label.split())
    res = await db.scalars(select(Festival))
    existing = list(res.all())
    for candidate in (label, *body.aliases):
        dup = match(candidate, existing, loose=False)
        if dup is not None:
            raise error(409, "festival_exists", f"“{candidate}” matches the existing festival “{dup.label}”.", festival_id=dup.id)
    fid = slugify(label)
    if not fid:
        raise error(422, "invalid_label", "Use letters or numbers in the festival name.")
    f = Festival(id=fid, label=label, aliases=[a.strip() for a in body.aliases if a.strip()], next_date=body.next_date, sort_order=1000)
    db.add(f)
    await db.commit()
    return FestivalOut(id=f.id, label=f.label, aliases=f.aliases, next_date=f.next_date)
