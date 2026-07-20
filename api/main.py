"""
api/main.py — FastAPI application factory for Nexora.

Nexora is a Telegram AI Knowledge Retrieval Platform powered by RAG.
Telegram is the sole external messaging data source.

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
from api.routes import collections, health, query, telegram
from api.logging_config import setup_logging
from asgi_correlation_id import CorrelationIdMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

setup_logging(log_level="INFO")
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

    logger.info(
        "Nexora API starting.  version=%s  vectors_root=%s",
        settings.version,
        settings.vectors_root,
    )

    import asyncio
    from app.integrations.telegram.client.mock_telegram_client import MockTelegramClientGateway
    from app.integrations.telegram.updates.update_router import TelegramUpdateRouter
    from app.integrations.telegram.repositories.checkpoint_repo import SqliteTelegramCheckpointRepository
    from app.integrations.telegram.services.sync_worker import TelegramSyncWorker
    from app.integrations.telegram.db.engine import get_session as engine_get_session, DatabaseSettings

    db_path = str(settings.vectors_root.parent / "storage" / "nexora_telegram.db")

    def session_factory():
        return engine_get_session(DatabaseSettings(db_path=db_path))

    client = MockTelegramClientGateway()
    router = TelegramUpdateRouter(session_factory=session_factory)
    checkpoint_repo = SqliteTelegramCheckpointRepository()

    worker = TelegramSyncWorker(
        client=client,
        router=router,
        checkpoint_repo=checkpoint_repo,
        session_factory=session_factory,
    )

    worker_task = asyncio.create_task(worker.start())

    yield

    # ── Shutdown ──────────────────────────────────────────────────────
    logger.info("Nexora API shutting down.")
    await worker.stop()
    await worker_task



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
            "Nexora — Telegram AI Knowledge Retrieval Platform. "
            "Powered by Retrieval-Augmented Generation (RAG). "
            "Telegram is the sole external messaging data source."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Security Middlewares
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins if hasattr(settings, "cors_origins") else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*"] # Can be restricted via env
    )

    # Observability Middlewares
    app.add_middleware(CorrelationIdMiddleware)
    Instrumentator().instrument(app).expose(app)

    # Register domain exception handlers
    register_handlers(app)

    # Register routers
    app.include_router(health.router)
    app.include_router(query.router)
    app.include_router(collections.router)
    app.include_router(telegram.router)

    return app


# ---------------------------------------------------------------------------
# Module-level app instance (used by uvicorn)
# ---------------------------------------------------------------------------

app: FastAPI = create_app()
