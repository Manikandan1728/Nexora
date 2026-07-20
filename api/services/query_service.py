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
    TelegramSourceResponse,
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
    authenticated_owner_id: Optional[str] = None,
) -> QueryResponse:
    """
    Execute Phase 5 retrieval and, optionally, Phase 6 RAG generation.

    Args:
        question:               The user's question.
        collection_name:        ChromaDB collection to search.
        top_k:                  Maximum number of results to retrieve.
        filters:                Optional metadata filter dict for Phase 5.
                                If the dict contains Telegram identity fields
                                (owner_id, source, conversation_id, sender_id,
                                etc.) they are routed through QueryScopeBuilder
                                + ChromaWhereBuilder for secure filter
                                construction. Legacy fields (source_chat, etc.)
                                continue to use the existing MetadataFilter path.
        use_rag:                Whether to attempt Phase 6 generation.
        settings:               Injected API settings.
        authenticated_owner_id: When provided, enforces owner isolation via
                                QueryScopeBuilder. When None, legacy filter
                                path is used (backward-compat).

    Returns:
        ``QueryResponse`` with retrieved documents, Telegram sources, and
        optional RAG answer.

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
        from app.retrieval.telegram_filter import (
            TelegramMetadataFilter,
            QueryScopeBuilder,
            ChromaWhereBuilder,
        )

        # Determine whether to use the new Telegram-aware filter path
        _TELEGRAM_FILTER_FIELDS = {
            "owner_id", "source", "source_account_id", "conversation_id",
            "conversation_ids", "sender_id", "content_type", "content_types",
            "source_message_id", "timestamp_from", "timestamp_to",
        }
        filters_dict = filters or {}
        has_telegram_fields = bool(
            _TELEGRAM_FILTER_FIELDS & set(filters_dict.keys())
        )

        where_clause: Optional[Dict] = None
        effective = None  # set only when Telegram filter path is used

        if has_telegram_fields or authenticated_owner_id:
            # New Telegram-aware path: QueryScopeBuilder + ChromaWhereBuilder
            tg_filter = TelegramMetadataFilter(**{
                k: v for k, v in filters_dict.items()
                if k in TelegramMetadataFilter.__dataclass_fields__
            })
            tg_filter.validate()

            scope_builder = QueryScopeBuilder()
            owner = authenticated_owner_id or filters_dict.get("owner_id", "anonymous")
            effective = scope_builder.build(
                authenticated_owner_id=owner,
                requested_filters=tg_filter,
            )
            logger.info(
                "QueryScopeBuilder: owner=%r conv=%r sender=%r source=%r",
                effective.owner_id,
                effective.conversation_id or effective.conversation_ids,
                effective.sender_id,
                effective.source,
            )

            chroma_builder = ChromaWhereBuilder()
            where_clause = chroma_builder.build(effective)
            logger.info(
                "ChromaWhereBuilder: filter built (%d conditions)",
                _count_conditions(where_clause),
            )
        else:
            # Legacy path: existing MetadataFilter (unchanged behavior)
            if filters_dict:
                from app.retrieval.metadata_filter import MetadataFilter
                where_clause = MetadataFilter().build(filters_dict)

        ret_cfg = RetrievalConfig(
            collection_name=collection_name,
            persist_directory=str(settings.vectors_root),
            embedding_model="BAAI/bge-m3",
            top_k=top_k,
            score_threshold=0.0,
            distance_metric="cosine",
        )
        retrieval_pipeline = RetrievalPipeline(config=ret_cfg)
        retrieved = retrieval_pipeline.search(
            query=question,
            filters=None,  # where_clause injected directly below
        )

        # Re-search with the validated where clause (bypass RetrievalPipeline's
        # filter builder so ChromaWhereBuilder is the sole constructor)
        if where_clause is not None:
            from app.retrieval.query_embedder import QueryEmbedder
            from app.retrieval.query_preprocessor import QueryPreprocessor
            from app.retrieval.similarity_search import SimilaritySearch

            clean_q = QueryPreprocessor.preprocess(question)
            embedder = QueryEmbedder()
            q_vec = embedder.embed(clean_q)
            searcher = SimilaritySearch(config=ret_cfg)
            retrieved = searcher.search(
                query_embedding=q_vec,
                query_text=clean_q,
                where=where_clause,
            )

        retrieval_pipeline.close()

        # ── Phase 14: is_deleted defense for Telegram source ─────────
        # [BREAKING-INTENTIONAL] scoped to source=telegram only.
        # Non-Telegram records that lack the is_deleted field are unaffected
        # because we only filter when source=="telegram" AND is_deleted==True.
        # Regression test: test_non_telegram_unaffected_by_is_deleted_filter
        if has_telegram_fields or authenticated_owner_id:
            retrieved = [
                r for r in retrieved
                if not (
                    r.metadata.get("source") == "telegram"
                    and r.metadata.get("is_deleted") is True
                )
            ]

        # ── Phase 6: Timestamp post-filter (application-level) ───────
        # [REFACTOR-SAFE] no-op when no timestamp bounds are set.
        if has_telegram_fields or authenticated_owner_id:
            from app.retrieval.timestamp_filter import (
                apply_timestamp_postfilter, TimestampFilterConfig,
            )
            ts_from = effective.timestamp_from if effective else None
            ts_to   = effective.timestamp_to   if effective else None
            if ts_from is not None or ts_to is not None:
                cfg = TimestampFilterConfig()
                logger.info(
                    "TimestampPostFilter: candidates=%d top_k=%d from=%s to=%s",
                    len(retrieved), top_k,
                    ts_from.isoformat() if ts_from else None,
                    ts_to.isoformat() if ts_to else None,
                )
                retrieved = apply_timestamp_postfilter(
                    results=retrieved,
                    timestamp_from=ts_from,
                    timestamp_to=ts_to,
                    top_k=top_k,
                    config=cfg,
                )

        from app.retrieval.snippet_extraction import extract_snippet
        from dataclasses import replace

        updated_retrieved = []
        for doc in retrieved:
            snippet_res = extract_snippet(question, doc.text)
            # Convert MessageRef objects to dicts for JSON serialisation
            matched_messages_dicts = None
            if snippet_res.matched_messages:
                matched_messages_dicts = [
                    {"text": mr.text, "index": mr.index}
                    for mr in snippet_res.matched_messages
                ]
            updated_doc = replace(
                doc,
                focused_snippet=snippet_res.focused_snippet,
                matched_messages=matched_messages_dicts,
                matched_terms=snippet_res.matched_terms,
                relevance_reason=snippet_res.relevance_reason,
                no_strong_passage=snippet_res.no_strong_passage if snippet_res.no_strong_passage else None,
            )
            updated_retrieved.append(updated_doc)
        retrieved = updated_retrieved

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
    no_strong_match = True
    if retrieved:
        no_strong_match = all(r.is_low_confidence for r in retrieved)

    def _meta_str(meta: dict, key: str) -> Optional[str]:
        v = meta.get(key)
        return str(v) if v is not None and str(v).strip() else None

    retrieved_docs = [
        RetrievedDocumentResponse(
            document_id=r.document_id,
            text=r.text,
            similarity_score=r.similarity_score,
            rank=r.rank,
            metadata=r.metadata,
            focused_snippet=r.focused_snippet,
            matched_messages=r.matched_messages,
            matched_terms=r.matched_terms,
            relevance_reason=r.relevance_reason,
            is_low_confidence=r.is_low_confidence,
            no_strong_passage=r.no_strong_passage,
            # Telegram identity fields from stored metadata [Req 11]
            owner_id=_meta_str(r.metadata, "owner_id"),
            source=_meta_str(r.metadata, "source"),
            source_account_id=_meta_str(r.metadata, "source_account_id"),
            conversation_id=_meta_str(r.metadata, "conversation_id"),
            conversation_title=_meta_str(r.metadata, "conversation_title"),
            conversation_type=_meta_str(r.metadata, "conversation_type"),
            sender_id=_meta_str(r.metadata, "sender_id"),
            sender_name=_meta_str(r.metadata, "sender_name"),
            source_message_id=_meta_str(r.metadata, "source_message_id"),
            content_type=_meta_str(r.metadata, "content_type"),
            timestamp=_meta_str(r.metadata, "timestamp"),
            filename=_meta_str(r.metadata, "filename"),
            mime_type=_meta_str(r.metadata, "mime_type"),
        )
        for r in retrieved
    ]

    # Build Telegram source citations [Req 12]
    sources = _build_telegram_sources(retrieved)

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
        sources=sources,
        confidence=confidence,
        llm_used=llm_used,
        message=rag_message,
        no_strong_match=no_strong_match,
        elapsed_seconds=round(elapsed, 3),
    )


def _count_conditions(where: Optional[Dict]) -> int:
    """Count top-level conditions in a ChromaDB where clause."""
    if not where:
        return 0
    if "$and" in where:
        return len(where["$and"])
    return 1


def _build_telegram_sources(retrieved: list) -> "list[TelegramSourceResponse]":
    """
    Build TelegramSourceResponse objects from retrieved documents.

    Deduplication rule (Req 12):
    - Chunks sharing (source_message_id, content_type) with no differentiating
      fields: keep only the highest-scoring one.
    - Chunks with distinct page_number / slide_number / transcript_segment:
      preserve separately (each carries different information).
    """
    if not retrieved:
        return []

    telegram_docs = [
        r for r in retrieved
        if r.metadata.get("source") == "telegram"
        or bool(r.metadata.get("owner_id"))
    ]
    if not telegram_docs:
        return []

    seen: dict[str, TelegramSourceResponse] = {}
    sources: list[TelegramSourceResponse] = []

    for r in telegram_docs:
        meta = r.metadata
        msg_id  = str(meta.get("source_message_id", ""))
        ct      = str(meta.get("content_type", "text"))
        page_no = str(meta.get("page_number", ""))
        slide   = str(meta.get("slide_number", ""))
        seg     = str(meta.get("transcript_segment", ""))
        dedup_key = f"{msg_id}:{ct}:{page_no}:{slide}:{seg}"

        snippet = (r.focused_snippet or r.text or "")[:200]

        src = TelegramSourceResponse(
            document_id=r.document_id,
            source=str(meta.get("source", "telegram")),
            conversation_id=str(meta.get("conversation_id", "")),
            conversation_title=str(meta.get("conversation_title", "") or meta.get("source_chat", "")),
            conversation_type=str(meta.get("conversation_type", "")),
            sender_id=str(meta.get("sender_id", "")),
            sender_name=str(meta.get("sender_name", "")),
            message_id=msg_id,
            timestamp=str(meta.get("timestamp", "")),
            content_type=ct,
            filename=str(meta.get("filename", "")),
            chunk_index=int(meta.get("chunk_index", 0)),
            snippet=snippet,
            score=r.similarity_score,
        )

        if dedup_key not in seen:
            seen[dedup_key] = src
            sources.append(src)
        elif src.score > seen[dedup_key].score:
            idx = sources.index(seen[dedup_key])
            sources[idx] = src
            seen[dedup_key] = src

    logger.debug(
        "query_service: assembled %d source citation(s) from %d Telegram chunks.",
        len(sources), len(telegram_docs),
    )
    return sources


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

    if llm_cfg.provider == "openai":
        from llm.openai_provider import OpenAIProvider
        provider: ILLMProvider = OpenAIProvider(llm_cfg)
    else:
        from llm.ollama_provider import OllamaProvider
        provider = OllamaProvider(llm_cfg)

    try:
        healthy = provider.health_check()
    except Exception as exc:
        raise LLMUnavailableError(f"LLM provider unreachable: {exc}") from exc

    if not healthy:
        raise LLMUnavailableError("LLM provider health check returned False.")

    from app.generation.phase6_pipeline import Phase6Pipeline
    gen_pipeline = Phase6Pipeline(provider=provider, config=llm_cfg)

    result = [None]
    error = [None]
    timeout = settings.llm_timeout_seconds + 5.0

    def _run() -> None:
        try:
            result[0] = gen_pipeline.run(question=question, retrieved_documents=retrieved)
        except Exception as exc:
            error[0] = exc

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout)
    provider.close()

    if t.is_alive():
        raise LLMUnavailableError(f"LLM generation timed out after {timeout:.0f}s.")
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
