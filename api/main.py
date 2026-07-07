"""
api/main.py — FastAPI application factory for Nexora Phase 7.

Responsibilities:
  - Create the ``FastAPI`` app with lifespan context manager.
  - Register all routers.
  - Register all exception handlers.
  - Initialise ``APISettings`` at startup (no heavy model loading here —
    embedding model and LLM clients are lazy-loaded by the engine).

No pipeline logic lives here.  The app is a thin transport layer over the
Phase 1-6 engine.

Usage:
    uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from api.config import get_settings
from api.error_handlers import register_handlers
from api.routes import collections, health, query, upload

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Manage application lifespan.

    Startup:
      - Loads and validates ``APISettings``.
      - Creates the upload directory if it doesn't exist.
      - Stores settings on ``app.state`` for dependency injection.

    Shutdown:
      - Logs clean exit (no persistent resources to release here;
        ChromaDB clients are opened/closed per-request in services).

    Note: The BGE-M3 embedding model and LLM clients are lazy-loaded
    on the first actual request — not here.  This keeps startup fast and
    avoids requiring GPU/network access just to start the server.
    """
    # ── Startup ───────────────────────────────────────────────────────
    settings = get_settings()
    app.state.settings = settings

    # Ensure the upload directory exists
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Nexora API starting.  version=%s  upload_dir=%s  vectors_root=%s",
        settings.version,
        settings.upload_dir,
        settings.vectors_root,
    )

    yield

    # ── Shutdown ──────────────────────────────────────────────────────
    logger.info("Nexora API shutting down.")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        A fully configured ``FastAPI`` instance ready to serve requests.
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description=(
            "Nexora Phase 7 — REST API over the Nexora WhatsApp knowledge engine. "
            "Exposes Phase 1-6 pipeline functionality via HTTP endpoints."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Register domain exception handlers
    register_handlers(app)

    # Register routers
    app.include_router(health.router)
    app.include_router(upload.router)
    app.include_router(query.router)
    app.include_router(collections.router)

    return app


# ---------------------------------------------------------------------------
# Module-level app instance (used by uvicorn)
# ---------------------------------------------------------------------------

app: FastAPI = create_app()
