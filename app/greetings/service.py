"""Async service layer for templates, assets, and greetings rendering using unified AsyncSession."""
from __future__ import annotations

from datetime import datetime, timezone
from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from greeting_renderer.festivals import SEED
from greeting_renderer.layout import clean_text
from greeting_renderer.render import render, to_jpeg

from app.models import Asset, Festival, Template
from . import storage
from .config import greeting_settings
from .schemas import AssetOut, Canvas, TemplateOut, TextField


def error(code: int, slug: str, message: str, **extra) -> HTTPException:
    return HTTPException(code, detail={"code": slug, "message": message, **extra})


def public_base(request: Request) -> str:
    return (greeting_settings.public_base_url or str(request.base_url)).rstrip("/")


def thumb_key(asset_id: str) -> str:
    return f"{storage.THUMBS}/{asset_id}-480.jpg"


def asset_out(asset: Asset) -> AssetOut:
    return AssetOut(
        id=asset.id,
        url=storage.url_for(asset.storage_key),
        thumbnail_url=storage.url_for(thumb_key(asset.id)),
        file_name=asset.file_name,
        mime_type=asset.mime_type,
        bytes=asset.bytes,
        width=asset.width,
        height=asset.height,
    )


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def template_out(t: Template) -> TemplateOut:
    return TemplateOut(
        id=t.id,
        name=t.name,
        festival_id=t.festival_id,
        festival_label=t.festival.label if t.festival else None,
        status="inactive" if not t.is_active else "live" if t.is_ready else "draft",
        active=bool(t.is_active),
        version=t.version,
        canvas=Canvas(width=t.canvas_width, height=t.canvas_height),
        background=asset_out(t.background) if t.background else None,
        fields=[TextField.model_validate(f) for f in (t.fields or [])],
        created_at=_utc(t.created_at),
        updated_at=_utc(t.updated_at),
        updated_by=t.updated_by,
    )


async def get_template(db: AsyncSession, template_id: str) -> Template:
    stmt = (
        select(Template)
        .options(joinedload(Template.festival), joinedload(Template.background))
        .where(Template.id == template_id)
    )
    res = await db.scalars(stmt)
    t = res.first()
    if t is None:
        raise error(status.HTTP_404_NOT_FOUND, "template_not_found", "This template doesn't exist or was deleted.")
    return t


async def get_asset(db: AsyncSession, asset_id: str | None) -> Asset | None:
    if asset_id is None:
        return None
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise error(status.HTTP_422_UNPROCESSABLE_ENTITY, "asset_not_found", "Background image not found. Upload it again.")
    return asset


async def template_for_festival(db: AsyncSession, festival_id: str) -> Template | None:
    stmt = (
        select(Template)
        .options(joinedload(Template.festival), joinedload(Template.background))
        .where(Template.festival_id == festival_id, Template.is_active.is_(True))
        .order_by(Template.updated_at.desc())
    )
    res = await db.scalars(stmt)
    return res.first()


async def claim_festival(db: AsyncSession, festival_id: str | None, template_id: str | None, replace: bool) -> None:
    """Ensure only one template is active per festival."""
    if festival_id is None:
        return
    stmt = (
        select(Template)
        .options(joinedload(Template.festival))
        .where(
            Template.festival_id == festival_id,
            Template.is_active.is_(True),
            Template.id != (template_id or ""),
        )
    )
    res = await db.scalars(stmt)
    others = res.all()
    if not others:
        return
    if not replace:
        o = others[0]
        raise error(
            status.HTTP_409_CONFLICT,
            "festival_taken",
            f"“{o.name}” is the active {o.festival.label if o.festival else festival_id} greeting.",
            templateId=o.id,
            templateName=o.name,
        )
    for o in others:
        o.is_active = False


async def live_templates(db: AsyncSession) -> list[Template]:
    """Retrieve all live templates, one per festival, sorted by festival order."""
    fest_res = await db.scalars(select(Festival))
    order = {f.id: (f.sort_order, f.label) for f in fest_res.all()}

    stmt = (
        select(Template)
        .options(joinedload(Template.festival), joinedload(Template.background))
        .where(Template.festival_id.is_not(None))
    )
    tmpl_res = await db.scalars(stmt)
    live = [t for t in tmpl_res.unique() if t.is_live]
    return sorted(live, key=lambda t: order.get(t.festival_id, (9999, "")))


async def seed_festivals(db: AsyncSession) -> None:
    """Seed festival categories and ensure default active templates exist."""
    # 1. Seed festivals
    res = await db.scalars(select(Festival.id))
    existing = set(res.all())
    for order, (fid, label, aliases) in enumerate(SEED):
        if fid not in existing:
            db.add(Festival(id=fid, label=label, aliases=aliases, sort_order=order))
    await db.commit()

    # 2. Migrate existing templates and assets from SQLite if present
    from pathlib import Path
    import json
    sqlite_path = Path("D:/sintex_template_feature/backend/data/greetings.db")
    if sqlite_path.exists():
        try:
            import sqlite3
            s_conn = sqlite3.connect(sqlite_path)
            s_conn.row_factory = sqlite3.Row
            s_cur = s_conn.cursor()

            s_cur.execute("SELECT * FROM assets")
            for a_row in s_cur.fetchall():
                a_dict = dict(a_row)
                asset_id = a_dict["id"]
                existing_asset = await db.get(Asset, asset_id)
                if not existing_asset:
                    new_asset = Asset(
                        id=asset_id,
                        file_name=a_dict.get("file_name", "image.jpg"),
                        mime_type=a_dict.get("mime_type", "image/jpeg"),
                        bytes=a_dict.get("bytes", 0),
                        width=a_dict.get("width", 1080),
                        height=a_dict.get("height", 1620),
                        storage_key=a_dict.get("storage_key", f"assets/{asset_id}.jpg"),
                    )
                    db.add(new_asset)
            await db.commit()

            tmpl_res = await db.scalars(select(Template.id))
            existing_templates = set(tmpl_res.all())

            s_cur.execute("SELECT * FROM templates")
            for t_row in s_cur.fetchall():
                t_dict = dict(t_row)
                t_id = t_dict["id"]
                if t_id not in existing_templates:
                    raw_fields = t_dict.get("fields")
                    fields_data = json.loads(raw_fields) if isinstance(raw_fields, str) else (raw_fields or [])
                    new_tmpl = Template(
                        id=t_id,
                        name=t_dict.get("name", "Greeting Template"),
                        festival_id=t_dict.get("festival_id"),
                        is_active=bool(t_dict.get("is_active", 1)),
                        version=t_dict.get("version", 1),
                        canvas_width=t_dict.get("canvas_width", 1080),
                        canvas_height=t_dict.get("canvas_height", 1620),
                        background_asset_id=t_dict.get("background_asset_id"),
                        fields=fields_data,
                    )
                    db.add(new_tmpl)
            await db.commit()
            s_conn.close()
        except Exception:
            pass

    # 3. Ensure a default active Diwali template exists so rendering works out of the box
    diwali_tmpl = await template_for_festival(db, "diwali")
    refined_fields = [
        {
            "id": "firm_name",
            "kind": "variable",
            "variable": "enterprise",
            "label": "Enterprise / Firm Name",
            "box": {"x": 180, "y": 1255, "width": 720},
            "style": {"fontFamily": "poppins", "fontWeight": 700, "fontSize": 44, "color": "#8B0000", "align": "center", "shadow": False, "textCase": "upper"},
            "fit": {"minFontSize": 24, "maxLines": 1},
            "whenEmpty": {"mode": "hide", "text": ""}
        },
        {
            "id": "user_name",
            "kind": "variable",
            "variable": "name",
            "label": "User Name",
            "box": {"x": 180, "y": 1325, "width": 720},
            "style": {"fontFamily": "poppins", "fontWeight": 600, "fontSize": 36, "color": "#1A1A1A", "align": "center", "shadow": False, "textCase": "title"},
            "fit": {"minFontSize": 20, "maxLines": 1},
            "whenEmpty": {"mode": "hide", "text": ""}
        },
        {
            "id": "user_phone",
            "kind": "variable",
            "variable": "number",
            "label": "Mobile Number",
            "box": {"x": 180, "y": 1390, "width": 720},
            "style": {"fontFamily": "poppins", "fontWeight": 500, "fontSize": 26, "color": "#4B5563", "align": "center", "shadow": False},
            "fit": {"minFontSize": 18, "maxLines": 1},
            "whenEmpty": {"mode": "hide", "text": ""}
        }
    ]
    festivals_to_ensure = [
        ("diwali", "diwali_default", "Diwali Festive Card"),
        ("dussehra", "dussehra_default", "Dussehra Festive Card"),
        ("pongal", "pongal_default", "Pongal Festive Card"),
        ("ganesh-chaturthi", "ganesh_chaturthi_default", "Ganesh Chaturthi Festive Card"),
    ]
    bg_asset_id = diwali_tmpl.background_asset_id if diwali_tmpl else None

    for f_id, t_id, t_name in festivals_to_ensure:
        tmpl = await template_for_festival(db, f_id)
        if not tmpl:
            t = Template(
                id=t_id,
                name=t_name,
                festival_id=f_id,
                is_active=True,
                canvas_width=1080,
                canvas_height=1620,
                background_asset_id=bg_asset_id,
                fields=refined_fields,
            )
            db.add(t)
            await db.commit()
        else:
            if not tmpl.fields:
                tmpl.fields = refined_fields
            if not tmpl.is_active:
                tmpl.is_active = True
            if not tmpl.background_asset_id and bg_asset_id:
                tmpl.background_asset_id = bg_asset_id
            await db.commit()



def render_template(t: Template, values: dict[str, str | None]) -> bytes:
    """Renders to JPEG bytes in memory using the exact styles, fonts, colors,
    and field boxes designed and saved in the Template Studio frontend."""
    from greeting_renderer.layout import to_title_camel_case

    cleaned = {}
    for k, v in values.items():
        if k == "name":
            cleaned[k] = to_title_camel_case(v)
        else:
            cleaned[k] = clean_text(v)

    has_phone = bool(cleaned.get("number"))
    if has_phone:
        raw_num = cleaned["number"]
        digits = "".join(c for c in str(raw_num) if c.isdigit())
        if len(digits) == 12 and digits.startswith("91"):
            cleaned["number"] = f"+91 {digits[2:7]} {digits[7:]}"
        elif len(digits) == 10:
            cleaned["number"] = f"+91 {digits[:5]} {digits[5:]}"

    raw_fields = t.fields or []
    fields: list[TextField] = []

    for f in raw_fields:
        if isinstance(f, TextField):
            fields.append(f)
        elif isinstance(f, dict):
            fields.append(TextField.model_validate(f))

    # If the template had no fields at all (e.g. empty draft), provide default layout
    if not fields:
        firm_y = 1255 if has_phone else 1285
        name_y = 1325 if has_phone else 1365
        phone_y = 1390
        firm_size = 44 if has_phone else 48
        name_size = 36 if has_phone else 40
        phone_size = 26
        default_defs = [
            {
                "id": "firm_name",
                "kind": "variable",
                "variable": "enterprise",
                "label": "Enterprise / Firm Name",
                "box": {"x": 180, "y": firm_y, "width": 720},
                "style": {"fontFamily": "poppins", "fontWeight": 700, "fontSize": firm_size, "color": "#8B0000", "align": "center", "shadow": False, "textCase": "upper"},
                "fit": {"minFontSize": 24, "maxLines": 1},
                "whenEmpty": {"mode": "hide", "text": ""}
            },
            {
                "id": "user_name",
                "kind": "variable",
                "variable": "name",
                "label": "User Name",
                "box": {"x": 180, "y": name_y, "width": 720},
                "style": {"fontFamily": "poppins", "fontWeight": 600, "fontSize": name_size, "color": "#1A1A1A", "align": "center", "shadow": False, "textCase": "title"},
                "fit": {"minFontSize": 20, "maxLines": 1},
                "whenEmpty": {"mode": "hide", "text": ""}
            },
        ]
        if has_phone:
            default_defs.append({
                "id": "user_phone",
                "kind": "variable",
                "variable": "number",
                "label": "Mobile Number",
                "box": {"x": 180, "y": phone_y, "width": 720},
                "style": {"fontFamily": "poppins", "fontWeight": 500, "fontSize": phone_size, "color": "#4B5563", "align": "center", "shadow": False},
                "fit": {"minFontSize": 18, "maxLines": 1},
                "whenEmpty": {"mode": "hide", "text": ""}
            })
        fields = [TextField.model_validate(fd) for fd in default_defs]

    background = None
    if t.background and t.background.storage_key:
        try:
            bg_path = storage.path_for(t.background.storage_key)
            if bg_path.exists():
                background = bg_path
        except Exception:
            background = None
    return to_jpeg(render(t.canvas_width, t.canvas_height, background, fields, cleaned), greeting_settings.max_render_bytes)


