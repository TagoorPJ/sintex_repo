from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy import text

from app.api.routes.chat import router as chat_router
from app.database import Base, engine
from app.utils.logger import get_logger
from app.api.routes.qr_capture import router as qr_router
load_dotenv()
logger = get_logger(__name__)


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("Starting up — creating DB tables if not exist")
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
    yield
    logger.info("Shutting down — disposing DB engine")
    await engine.dispose()


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Enterprise Chatbot API",
    description="LangGraph-based ReAct agent for B2B user onboarding",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount static files and setup Jinja2 templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ─── CORS ─────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Global exception handler ─────────────────────────────────────────────────

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

# ─── Routes ───────────────────────────────────────────────────────────────────

app.include_router(chat_router, prefix="/api/v1")

app.include_router(qr_router, prefix="/api/v1")

@app.get("/health", tags=["health"])
async def health_check() -> dict:
    return {"status": "ok", "service": "syntex_agent_running"}


@app.get("/scanner", tags=["web"])
async def scanner(request: Request):
    """Alternative path for the QR scanner page."""
    return templates.TemplateResponse("index.html", {"request": request})



# ─── Dev runner ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("APP_ENV", "development") == "development",
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )
