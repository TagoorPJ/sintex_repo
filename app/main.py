from __future__ import annotations

import asyncio
import json
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy import text

from greeting_renderer.fonts import FONTS_DIR, manifest
from PIL import features

from app.api.routes.chat import router as chat_router
from app.api.routes.qr_capture import router as qr_router
from app.database import AsyncSessionLocal, Base, engine
from app.greetings import storage
from app.greetings.config import greeting_settings
from app.greetings.routers import (
    assets_router,
    cards_router,
    festivals_router,
    greetings_router,
    templates_router,
)
from app.greetings.security import require_admin
from app.greetings.service import seed_festivals
from app.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)


# ─── Periodic Sweeper ─────────────────────────────────────────────────────────

async def _sweep_cards_forever() -> None:
    """Periodically sweep uncollected one-time greeting cards past TTL."""
    while True:
        try:
            storage.sweep_cards(greeting_settings.render_ttl_seconds)
        except Exception as exc:
            logger.warning(f"Error in card outbox sweeper: {exc}")
        await asyncio.sleep(60)


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle for unified application."""
    logger.info("Starting up — creating DB tables if not exist (unified ORM)")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Ensure new columns exist on users table for existing databases
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(150);")
        )
        await conn.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS registered_via_chatbot "
                "BOOLEAN NOT NULL DEFAULT FALSE;"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS registered_at "
                "TIMESTAMP WITH TIME ZONE;"
            )
        )
    logger.info("Database tables ready")

    # Seed festivals in database if not present
    try:
        async with AsyncSessionLocal() as session:
            await seed_festivals(session)
        logger.info("Festivals verified / seeded")
    except Exception as exc:
        logger.error(f"Failed to seed festivals: {exc}", exc_info=True)

    # Ensure storage directories exist
    greeting_settings.storage_dir.mkdir(parents=True, exist_ok=True)
    greeting_settings.outbox_dir.mkdir(parents=True, exist_ok=True)

    sweeper = asyncio.create_task(_sweep_cards_forever())
    yield
    sweeper.cancel()
    logger.info("Shutting down — disposing DB engine")
    await engine.dispose()


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Sintex Enterprise AI & Greeting Studio API",
    description="Unified LangGraph ReAct Agent, Onboarding, Claims, and Festive Greeting Template Studio",
    version="1.0.0",
    lifespan=lifespan,
)

# ─── Mount Static Files & Templates ───────────────────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Mount media directory for greeting background assets and thumbnails
greeting_settings.storage_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=greeting_settings.storage_dir), name="media")

# Mount fonts directory for canvas preview
if FONTS_DIR.exists():
    app.mount("/fonts", StaticFiles(directory=FONTS_DIR), name="fonts")

# Mount React Frontend Studio if built
frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
fallback_dist = Path("D:/sintex_template_feature/frontend/dist")
studio_path = frontend_dist if frontend_dist.exists() else (fallback_dist if fallback_dist.exists() else None)

if studio_path:
    @app.get("/studio/env.js", tags=["studio"])
    async def studio_env_js():
        """
        Dynamically generates runtime environment config for Greeting Template Studio
        from server .env (PUBLIC_BASE_URL).
        """
        public_base = (greeting_settings.public_base_url or "").rstrip("/")
        if public_base:
            parsed = urlparse(public_base)
            prefix = parsed.path.rstrip("/")
            studio_base = f"{prefix}/studio" if prefix else "/studio"
            api_url = public_base
        else:
            studio_base = "/studio"
            api_url = ""

        content = (
            f"// Dynamic runtime configuration generated from server .env\n"
            f"window.__ENV__ = window.__ENV__ || {{}};\n"
            f"window.__ENV__.API_URL = {json.dumps(api_url)};\n"
            f"window.__ENV__.STUDIO_BASE = {json.dumps(studio_base)};\n"
        )
        return Response(content=content, media_type="application/javascript")

    @app.get("/studio", tags=["studio"])
    async def studio_root_index():
        """Directly serve studio index.html to avoid reverse proxy slash-redirect issues."""
        idx = studio_path / "index.html"
        if idx.exists():
            return FileResponse(idx)
        return JSONResponse(status_code=404, content={"detail": "Studio index not found"})

    app.mount("/studio", StaticFiles(directory=studio_path, html=True), name="studio")

# ─── CORS ─────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Global Exception Handler ─────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled exception",
        extra={"path": request.url.path, "error": str(exc)},
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred."},
    )


# ─── Routers ──────────────────────────────────────────────────────────────────

# Chatbot & QR Scanner routes
app.include_router(chat_router, prefix="/api/v1")
app.include_router(qr_router, prefix="/api/v1")

# Greeting Template Studio Admin & Render routes
app.include_router(templates_router)
app.include_router(assets_router)
app.include_router(festivals_router)
app.include_router(greetings_router)
app.include_router(cards_router)


# ─── Health & Meta Endpoints ──────────────────────────────────────────────────

@app.get("/health", tags=["health"])
async def health_check() -> dict:
    return {
        "status": "ok",
        "service": "sintex_unified_app",
        "complex_scripts": bool(features.check("raqm")),
    }


@app.get("/api/fonts", tags=["meta"])
def fonts(request: Request):
    """Manifest of available fonts for greeting card rendering."""
    base = (greeting_settings.public_base_url or str(request.base_url)).rstrip("/")
    return manifest(base_url=base)


@app.get("/api/auth/check", tags=["meta"], dependencies=[Depends(require_admin)])
def auth_check():
    """Verify admin API key for Greeting Studio."""
    return {"ok": True}


@app.get("/scanner", tags=["web"])
async def scanner(request: Request):
    """Path for the QR scanner page."""
    return templates.TemplateResponse("index.html", {"request": request})


# ─── Dev Runner ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("APP_ENV", "development") == "development",
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )
