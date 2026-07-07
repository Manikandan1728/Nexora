"""
api/routes/query.py — POST /query

Validates the request, runs Phase 5 retrieval and optional Phase 6 RAG,
and returns ranked results with an optional grounded answer.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from api.config import APISettings, get_settings
from api.schemas.request_models import QueryRequest
from api.schemas.response_models import QueryResponse
from api.services import query_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["query"])


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Semantic search + optional RAG answer",
)
async def query(
    body: QueryRequest,
    settings: Annotated[APISettings, Depends(get_settings)],
) -> QueryResponse:
    """
    Run Phase 5 semantic retrieval against an indexed collection and,
    optionally, Phase 6 grounded answer generation.

    Behaviour when the LLM is unavailable:
    - Returns HTTP **200** (not 500).
    - ``answer`` field is ``null``.
    - ``llm_used`` is ``False``.
    - ``message`` explains that results are retrieval-only.

    Args:
        body:     Validated ``QueryRequest`` (question, collection, top_k …).
        settings: Injected ``APISettings``.

    Returns:
        ``QueryResponse`` with retrieved documents and optional RAG answer.
    """
    result: QueryResponse = await run_in_threadpool(
        query_service.run_query,
        body.question,
        body.collection_name,
        body.top_k,
        body.filters,
        body.use_rag,
        settings,
    )
    logger.info(
        "Query complete: collection=%s  results=%d  llm_used=%s",
        body.collection_name,
        len(result.retrieved_documents),
        result.llm_used,
    )
    return result
