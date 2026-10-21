from __future__ import annotations

import io
import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Asset
from .. import storage
from ..config import greeting_settings
from ..schemas import AssetOut
from ..security import require_admin
from ..service import asset_out, error, thumb_key

router = APIRouter(prefix="/api/assets", tags=["assets (admin)"], dependencies=[Depends(require_admin)])

FORMATS = {"PNG": ("image/png", "png"), "JPEG": ("image/jpeg", "jpg"), "WEBP": ("image/webp", "webp")}
MAX_SIDE = 4096


@router.post("", response_model=AssetOut, response_model_by_alias=True, status_code=201)
async def upload_asset(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    data = await file.read()
    if len(data) > greeting_settings.max_upload_bytes:
        mb = len(data) / 1024 / 1024
        raise error(413, "file_too_large", f"This image is {mb:.0f} MB. Use one under {greeting_settings.max_upload_bytes // 1024 // 1024} MB.")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise error(422, "unreadable_image", "We couldn't read this image. It may be damaged — try re-exporting it.") from exc
    if img.format not in FORMATS:
        raise error(415, "unsupported_type", f"{img.format or 'This'} files aren't supported. Export as JPG or PNG and try again.")

    mime, ext = FORMATS[img.format]
    oriented = ImageOps.exif_transpose(img)
    changed = oriented is not img
    if max(oriented.size) > MAX_SIDE:
        oriented.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
        changed = True
    if changed:
        buf = io.BytesIO()
        if img.format == "JPEG":
            oriented.convert("RGB").save(buf, "JPEG", quality=92)
        else:
            oriented.save(buf, img.format)
        data = buf.getvalue()

    asset_id = uuid.uuid4().hex
    key = f"{storage.ASSETS}/{asset_id}.{ext}"
    storage.save(key, data)

    thumb = oriented.convert("RGB")
    thumb.thumbnail((480, 480 * 3), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    thumb.save(buf, "JPEG", quality=82)
    storage.save(thumb_key(asset_id), buf.getvalue())

    asset = Asset(
        id=asset_id,
        file_name=(file.filename or f"image.{ext}")[:255],
        mime_type=mime,
        bytes=len(data),
        width=oriented.width,
        height=oriented.height,
        storage_key=key,
    )
    db.add(asset)
    await db.commit()
    return asset_out(asset)
