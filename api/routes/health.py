"""
api/routes/health.py — GET /health

Returns engine status and a lightweight LLM provider probe.
Must respond in under ~1 s regardless of LLM availability.
"""

from __future__ import annotations

import logging
import threading
from typing import Annotated

from fastapi import APIRouter, Depends

from api.config import APISettings, get_settings
from api.schemas.response_models import HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])

# ---------------------------------------------------------------------------
# Engine import probe — lazy, checked on first /health call
# ---------------------------------------------------------------------------
_ENGINE_OK: bool | None = None   # None = not yet checked
_ENGINE_ERROR: str = ""


def _check_engine() -> tuple[bool, str]:
    """
    Attempt to import all Phase 1-6 pipeline modules.

    Returns (ok, error_message).  Called at most once per process.
    Uses a module-level flag so repeated /health calls don't re-import.
    """
    global _ENGINE_OK, _ENGINE_ERROR
    if _ENGINE_OK is not None:
        return _ENGINE_OK, _ENGINE_ERROR
    try:
        from pipeline.phase1_pipeline import Phase1Pipeline  # noqa: F401
        from app.documents.phase2_pipeline import Phase2Pipeline  # noqa: F401
        from app.vectorization.embedding_pipeline import EmbeddingPipeline  # noqa: F401
        from app.storage.vector_store.phase4_pipeline import Phase4Pipeline  # noqa: F401
        from app.retrieval.retrieval_pipeline import RetrievalPipeline  # noqa: F401
        from app.generation.phase6_pipeline import Phase6Pipeline  # noqa: F401
        _ENGINE_OK = True
        _ENGINE_ERROR = ""
    except Exception as exc:
        _ENGINE_OK = False
        _ENGINE_ERROR = str(exc)
        logger.warning("Engine import probe failed: %s", exc)
    return _ENGINE_OK, _ENGINE_ERROR


def _probe_llm(settings: APISettings, result: list, timeout: float = 0.8) -> None:
    """
    Non-blocking health probe for the LLM provider.

    Runs in a daemon thread; the main thread joins with *timeout* seconds.
    Writes ``True``/``False`` into *result[0]*.
    """
    def _check() -> None:
        try:
            if settings.llm_provider == "openai":
                from llm.openai_provider import OpenAIProvider
                from config.llm_config import LLMConfig
                cfg = LLMConfig(provider="openai")
                ok = OpenAIProvider(cfg).health_check()
            else:
                from llm.ollama_provider import OllamaProvider
                from config.llm_config import LLMConfig
                cfg = LLMConfig(provider="ollama")
                ok = OllamaProvider(cfg).health_check()
            result[0] = ok
        except Exception:
            result[0] = False

    slot: list = [False]
    t = threading.Thread(target=_check, daemon=True)
    t.start()
    t.join(timeout=timeout)
    result[0] = slot[0] if not t.is_alive() else False


@router.get("/health", response_model=HealthResponse, summary="Engine health check")
async def health(
    settings: Annotated[APISettings, Depends(get_settings)],
) -> HealthResponse:
    """
    Return the current health status of the Nexora engine.

    Checks:
    - Whether Phase 1-6 modules imported successfully (cached at startup).
    - Whether the configured LLM provider is reachable (non-blocking probe
      with a hard 0.8 s timeout — never hangs this endpoint).

    Returns:
        ``HealthResponse`` with ``status``, ``engine_status``, and
        ``llm_provider_available``.
    """
    result: list = [False]
    _probe_llm(settings, result)
    llm_ok: bool = result[0]

    engine_ok, engine_err = _check_engine()
    engine_status = "ok" if engine_ok else f"error: {engine_err}"
    overall_status = "ok" if (engine_ok and llm_ok) else "degraded"

    return HealthResponse(
        status=overall_status,
        app_name=settings.app_name,
        version=settings.version,
        engine_status=engine_status,
        llm_provider_available=llm_ok,
    )
