"""
app/retrieval/retrieval_pipeline.py — Phase 5 orchestrator.

WHY THIS MODULE EXISTS
----------------------
Four sub-components each own a single concern:
  • ``QueryPreprocessor``  — clean and validate the raw query string
  • ``QueryEmbedder``      — convert the query to a vector
  • ``MetadataFilter``     — build the ChromaDB where clause
  • ``SimilaritySearch``   — execute the ANN search and rank results

``RetrievalPipeline`` wires them together in the correct order behind a
single entry point:

    results = RetrievalPipeline(config).search("What did Alice say?")

WHAT THIS PIPELINE DELIBERATELY DOES NOT DO
--------------------------------------------
  • No answer generation (Phase 6)
  • No LLM calls
  • No reranking or hybrid BM25 + dense search
  • No API endpoints
  • No UI
  • No mutation of retrieved documents

DEPENDENCY INJECTION
--------------------
Every collaborator is constructor-injectable so tests can supply mocks,
stub embedders, and real ChromaDB collections backed by ``tmp_path``
without touching production configuration.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

from models.retrieved_document import RetrievedDocument
from config.retrieval_config import RetrievalConfig
from app.retrieval.query_preprocessor import QueryPreprocessor
from app.retrieval.query_embedder import IQueryEmbedder, QueryEmbedder
from app.retrieval.metadata_filter import MetadataFilter
from app.retrieval.similarity_search import SimilaritySearch
from exceptions.exceptions import (
    QueryValidationError,
    QueryEmbeddingError,
    SimilaritySearchError,
    RetrievalError,
)

logger = logging.getLogger(__name__)


class RetrievalPipeline:
    """
    Orchestrates the full Phase 5 retrieval flow.

    Parameters
    ----------
    config : RetrievalConfig
        Retrieval configuration.  Defaults to ``RetrievalConfig()`` which
        reads from environment variables or uses project defaults.
    embedder : IQueryEmbedder, optional
        Query embedder.  Defaults to ``QueryEmbedder()`` (BGE-M3 singleton).
        Inject a fake embedder in tests to avoid loading model weights.
    similarity_search : SimilaritySearch, optional
        The search engine.  Defaults to ``SimilaritySearch(config)``.
        Inject a pre-configured searcher pointing to a ``tmp_path`` DB
        in tests.

    Example
    -------
    ::

        from config.retrieval_config import RetrievalConfig
        from app.retrieval.retrieval_pipeline import RetrievalPipeline

        config  = RetrievalConfig(persist_directory="data/vectors")
        results = RetrievalPipeline(config).search("What did Alice say?")
        for r in results:
            print(r.rank, r.similarity_score, r.text[:80])
    """

    def __init__(
        self,
        config: Optional[RetrievalConfig] = None,
        embedder: Optional[IQueryEmbedder] = None,
        similarity_search: Optional[SimilaritySearch] = None,
    ) -> None:
        self._config = config or RetrievalConfig()
        self._embedder: IQueryEmbedder = embedder or QueryEmbedder()
        self._search: SimilaritySearch = (
            similarity_search or SimilaritySearch(self._config)
        )
        self._preprocessor = QueryPreprocessor()
        self._filter_builder = MetadataFilter()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        filters: Optional[Dict] = None,
    ) -> List[RetrievedDocument]:
        """
        Run the full retrieval pipeline for *query*.

        Steps:
        1. Preprocess the query (clean, validate, normalise Unicode).
        2. Embed the preprocessed query using BGE-M3.
        3. Build a ChromaDB where-clause from *filters* (if provided and
           if ``config.enable_metadata_filtering`` is True).
        4. Execute ANN similarity search.
        5. Return ranked ``List[RetrievedDocument]``.

        Args:
            query:   Raw user query string.
            filters: Optional ``{field: value}`` or ``{field: {"$op": v}}``
                     dict.  Supported fields are listed in
                     ``MetadataFilter.supported_fields()``.

        Returns:
            Ranked list of ``RetrievedDocument`` objects, most similar first.
            Returns ``[]`` when the collection is empty, when no results
            pass the score threshold, or when metadata filters match nothing.

        Raises:
            QueryValidationError:  If the query is empty or otherwise invalid.
            QueryEmbeddingError:   If the embedding model fails.
            SimilaritySearchError: If the ChromaDB query fails.
            RetrievalError:        If the collection cannot be opened.
        """
        start = time.perf_counter()

        # ── Stage 1: Preprocess ──────────────────────────────────────
        clean_query = self._preprocessor.preprocess(query)
        logger.debug("Preprocessed query: %r", clean_query)

        # ── Stage 2: Embed ───────────────────────────────────────────
        query_vector = self._embedder.embed(clean_query)
        logger.debug(
            "Query embedded.  dim=%d  norm≈1", len(query_vector)
        )

        # ── Stage 3: Build metadata filter ───────────────────────────
        where_clause: Optional[Dict] = None
        if filters and self._config.enable_metadata_filtering:
            where_clause = self._filter_builder.build(filters)
            logger.debug("Metadata filter: %s", where_clause)

        # ── Stage 4: Similarity search ───────────────────────────────
        results = self._search.search(
            query_embedding=query_vector,
            query_text=clean_query,
            where=where_clause,
        )

        elapsed = time.perf_counter() - start
        logger.info(
            "RetrievalPipeline: query=%r  results=%d  elapsed=%.3fs",
            clean_query[:60],
            len(results),
            elapsed,
        )
        return results

    def close(self) -> None:
        """Release all held resources (ChromaDB client, etc.)."""
        self._search.close()
