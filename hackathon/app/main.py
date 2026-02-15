"""
2020 AI Agent — FastAPI application entry point.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import APP_TITLE, APP_VERSION
from app.routers import auth, phone, reports, triage, voice_interview
from app.services.events import event_manager
from app.services.telegram_bot import start_telegram_bot, stop_telegram_bot

# ── Logging ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)


# ── App Lifespan (startup/shutdown) ─────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background services on startup, stop on shutdown."""
    await start_telegram_bot()
    yield
    await stop_telegram_bot()


# ── App ─────────────────────────────────────────────────────
app = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    description=(
        "2020 AI Agent — AI-powered emergency triage system for natural disaster scenarios. "
        "Accepts voice calls and text reports, classifies severity, and "
        "generates actionable triage recommendations."
    ),
    lifespan=lifespan,
)

# CORS — allow all during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ─────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(triage.router)
app.include_router(reports.router)
app.include_router(phone.router)
app.include_router(voice_interview.router)

# ── Static files (frontend) ────────────────────────────────
_static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")


# ── Server-Sent Events (real-time dashboard) ───────────────
@app.get("/api/events", tags=["System"])
async def sse_stream(request: Request):
    """SSE endpoint for real-time dashboard updates."""

    async def generate():
        # Send initial keepalive
        yield "event: connected\ndata: {}\n\n"
        async for event in event_manager.subscribe():
            # Stop if client disconnects
            if await request.is_disconnected():
                break
            yield event

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Frontend (serve index.html at root) ────────────────────
@app.get("/", tags=["Frontend"])
async def serve_frontend():
    """Serve the frontend application."""
    return FileResponse(os.path.join(_static_dir, "index.html"))


# ── Health Check ────────────────────────────────────────────
@app.get("/health", tags=["System"])
@app.get("/api/health", tags=["System"])
async def health_check() -> dict:
    """Basic health check endpoint."""
    from datetime import datetime, timezone
    from app.services.report_store import store

    return {
        "status": "ok",
        "service": APP_TITLE,
        "version": APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_reports": await store.count(),
        "live_dashboard_clients": event_manager.client_count,
    }
