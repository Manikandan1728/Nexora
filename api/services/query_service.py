"""
api/services/query_service.py — Orchestrates Phase 5 and optionally Phase 6.

Phase 5 (retrieval) is always executed.
Phase 6 (RAG) is executed only when ``use_rag=True`` and the LLM provider
is reachable.  If Phase 6 fails or times out, the service falls back to
retrieval-only results and sets ``llm_used=False`` with an explanatory
``message`` — it never returns a 500 for LLM unavailability.

All pipeline calls are synchronous; the route layer wraps this function
in ``run_in_threadpool``.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from api.config import APISettings
from api.exceptions import (
    CollectionNotFoundError,
    InvalidInputError,
    LLMUnavailableError,
    ProcessingError,
)
from api.schemas.response_models import (
    CitationResponse,
    QueryResponse,
    RetrievedDocumentResponse,
)

logger = logging.getLogger(__name__)


def _collection_exists(collection_name: str, settings: APISettings) -> bool:
    """
    Return ``True`` if *collection_name* exists in the ChromaDB persist root.

    Opens a lightweight client, lists collections, and closes immediately.
    """
    vectors_dir = settings.vectors_root
    if not vectors_dir.exists():
        return False
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(vectors_dir))
        names = [c.name for c in client.list_collections()]
        return collection_name in names
    except Exception as exc:
        logger.warning("Could not verify collection existence: %s", exc)
        return False


def run_query(
    question: str,
    collection_name: str,
    top_k: int,
    filters: Optional[Dict[str, Any]],
    use_rag: bool,
    settings: APISettings,
) -> QueryResponse:
    """
    Execute Phase 5 retrieval and, optionally, Phase 6 RAG generation.

    Args:
        question:        The user's question.
        collection_name: ChromaDB collection to search.
        top_k:           Maximum number of results to retrieve.
        filters:         Optional metadata filter dict for Phase 5.
        use_rag:         Whether to attempt Phase 6 generation.
        settings:        Injected API settings.

    Returns:
        ``QueryResponse`` with retrieved documents and, if ``use_rag`` and
        the LLM was available, a grounded answer with citations.

    Raises:
        CollectionNotFoundError: If the collection does not exist.
        ProcessingError:         If Phase 5 raises an unexpected error.
    """
    wall_start = time.perf_counter()

    # ── Validate collection existence ─────────────────────────────────
    if not _collection_exists(collection_name, settings):
        raise CollectionNotFoundError(
            f"Collection '{collection_name}' does not exist."
        )

    # ── Phase 5 — Retrieval ───────────────────────────────────────────
    try:
        from config.retrieval_config import RetrievalConfig
        from app.retrieval.retrieval_pipeline import RetrievalPipeline

        ret_cfg = RetrievalConfig(
            collection_name=collection_name,
            persist_directory=str(settings.vectors_root),
            embedding_model="BAAI/bge-m3",
            top_k=top_k,
            score_threshold=0.0,
            distance_metric="cosine",
        )
        retrieval_pipeline = RetrievalPipeline(config=ret_cfg)
        retrieved = retrieval_pipeline.search(query=question, filters=filters)
        retrieval_pipeline.close()
        logger.info(
            "Phase 5 complete.  Results: %d  collection=%s",
            len(retrieved),
            collection_name,
        )
    except (CollectionNotFoundError, InvalidInputError):
        raise
    except Exception as exc:
        logger.error("Phase 5 failed: %s", exc)
        raise ProcessingError("Retrieval failed.") from exc

    # Build retrieval-only response objects
    retrieved_docs = [
        RetrievedDocumentResponse(
            document_id=r.document_id,
            text=r.text,
            similarity_score=r.similarity_score,
            rank=r.rank,
            metadata=r.metadata,
        )
        for r in retrieved
    ]

    # ── Phase 6 — RAG (optional) ──────────────────────────────────────
    answer_text: Optional[str] = None
    citations: List[CitationResponse] = []
    confidence: Optional[float] = None
    llm_used = False
    rag_message: Optional[str] = None

    if use_rag and retrieved:
        try:
            answer_text, citations, confidence = _run_rag(
                question=question,
                retrieved=retrieved,
                settings=settings,
            )
            llm_used = True
        except LLMUnavailableError as exc:
            rag_message = str(exc)
            logger.info("LLM unavailable; returning retrieval-only. Reason: %s", exc)
        except Exception as exc:
            rag_message = "LLM generation failed; retrieval-only results returned."
            logger.warning("Phase 6 error (non-fatal): %s", exc)
    elif use_rag and not retrieved:
        rag_message = "No documents retrieved; RAG skipped."

    elapsed = time.perf_counter() - wall_start

    return QueryResponse(
        question=question,
        answer=answer_text,
        citations=citations,
        retrieved_documents=retrieved_docs,
        confidence=confidence,
        llm_used=llm_used,
        message=rag_message,
        elapsed_seconds=round(elapsed, 3),
    )


def _run_rag(
    question: str,
    retrieved: list,
    settings: APISettings,
) -> tuple:
    """
    Run Phase 6 RAG generation.

    Args:
        question:   User question.
        retrieved:  List of ``RetrievedDocument`` objects from Phase 5.
        settings:   API settings (provides LLM config and timeout).

    Returns:
        ``(answer_text, citations, confidence)`` tuple.

    Raises:
        LLMUnavailableError: When the LLM provider is unreachable or times out.
        Exception:           For other Phase 6 failures.
    """
    import signal
    import threading

    from config.llm_config import LLMConfig
    from llm.interfaces import ILLMProvider

    # Build LLM config from API settings
    llm_kwargs: Dict[str, Any] = {
        "provider": settings.llm_provider,
        "timeout": settings.llm_timeout_seconds,
    }
    if settings.llm_model:
        llm_kwargs["model"] = settings.llm_model
    if settings.openai_api_key:
        llm_kwargs["api_key"] = settings.openai_api_key
    if settings.llm_base_url:
        llm_kwargs["base_url"] = settings.llm_base_url

    llm_cfg = LLMConfig(**llm_kwargs)

    # Select provider
    if llm_cfg.provider == "openai":
        from llm.openai_provider import OpenAIProvider
        provider: ILLMProvider = OpenAIProvider(llm_cfg)
    else:
        from llm.ollama_provider import OllamaProvider
        provider = OllamaProvider(llm_cfg)

    # Lightweight health-check before committing to a full generation call
    try:
        healthy = provider.health_check()
    except Exception as exc:
        raise LLMUnavailableError(
            f"LLM provider unreachable: {exc}"
        ) from exc

    if not healthy:
        raise LLMUnavailableError("LLM provider health check returned False.")

    # Run Phase 6
    from app.generation.phase6_pipeline import Phase6Pipeline
    gen_pipeline = Phase6Pipeline(provider=provider, config=llm_cfg)

    result = [None]
    error = [None]
    timeout = settings.llm_timeout_seconds + 5.0  # small buffer above LLM timeout

    def _run() -> None:
        try:
            result[0] = gen_pipeline.run(
                question=question,
                retrieved_documents=retrieved,
            )
        except Exception as exc:
            error[0] = exc

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout)

    provider.close()

    if t.is_alive():
        raise LLMUnavailableError(
            f"LLM generation timed out after {timeout:.0f}s."
        )
    if error[0] is not None:
        raise error[0]

    answer = result[0]
    if answer is None:
        raise LLMUnavailableError("Phase 6 returned no answer.")

    citations = [
        CitationResponse(
            document_id=c.document_id,
            rank=c.rank,
            similarity_score=c.similarity_score,
            source_chat=c.source_chat,
            chunk_index=c.chunk_index,
            start_timestamp=c.start_timestamp,
            end_timestamp=c.end_timestamp,
        )
        for c in answer.citations
    ]

    return answer.answer, citations, answer.confidence
