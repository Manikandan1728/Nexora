"""
app/retrieval/similarity_search.py — ChromaDB ANN search and result conversion.

WHY THIS MODULE EXISTS
----------------------
``SimilaritySearch`` is the only module in Phase 5 that touches the
ChromaDB collection directly.  It:

  1. Opens the existing Phase 4 collection (read-only semantics — it never
     calls add/delete/update).
  2. Executes ``collection.query()`` with the query embedding.
  3. Converts ChromaDB's raw distance values to similarity scores.
  4. Applies the score threshold to drop low-quality results.
  5. Wraps each result in a ``RetrievedDocument``.

DISTANCE → SIMILARITY CONVERSION
----------------------------------
ChromaDB returns distances, not similarities.  The conversion depends on
the index's distance metric:

  cosine  → similarity = 1 - distance          (distance ∈ [0, 2])
             For normalised vectors, distance ∈ [0, 2], so similarity ∈ [-1, 1].
             In practice, BGE-M3 vectors are normalised to unit norm, so
             distance ∈ [0, 2] and similarity ∈ [0, 1] for non-adversarial queries.
             We clamp to [0, 1] to handle floating-point edge cases.

  l2      → similarity = 1 / (1 + distance)    (distance ∈ [0, ∞))
             Monotonically decreasing, always in (0, 1].

  ip      → similarity = distance itself        (inner product ≈ cosine
             similarity for pre-normalised vectors; already in [-1, 1]).
             We clamp to [0, 1].

EMPTY COLLECTION / EMPTY RESULTS
----------------------------------
If the collection is empty or no results exceed the score threshold, an
empty list is returned — never None, never an exception.  This is
correct behaviour: "no results found" is not an error.

DEPENDENCY INJECTION
--------------------
``SimilaritySearch.__init__`` accepts an optional ``collection`` argument.
In tests, we inject a real ChromaDB collection backed by ``tmp_path``
rather than the production ``data/vectors`` directory.  This makes every
test fully self-contained with zero shared state.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import chromadb
from chromadb import Collection

from models.retrieved_document import RetrievedDocument
from config.retrieval_config import RetrievalConfig
from config.snippet_config import LOW_CONFIDENCE_THRESHOLD
from app.storage.vector_store.persistence import StoragePersistence
from app.storage.vector_store.collection_manager import CollectionManager
from config.vector_config import VectorStoreConfig
from exceptions.exceptions import SimilaritySearchError, RetrievalError

logger = logging.getLogger(__name__)


class SimilaritySearch:
    """
    Executes ANN similarity search against a ChromaDB collection.

    Parameters
    ----------
    config : RetrievalConfig
        Retrieval configuration (collection name, persist dir, top_k, etc.).
    collection : chromadb.Collection, optional
        Pre-opened ChromaDB collection.  When supplied, the ``config``'s
        ``persist_directory`` and ``collection_name`` are ignored for
        connection purposes — the injected collection is used directly.
        Intended for testing.

    Usage
    -----
    ::

        searcher = SimilaritySearch(config)
        results  = searcher.search(query_vector, query_text="What did Alice say?")
    """

    def __init__(
        self,
        config: RetrievalConfig,
        collection: Optional[Collection] = None,
    ) -> None:
        self._config = config
        self._collection: Optional[Collection] = collection
        self._persistence: Optional[StoragePersistence] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(
        self,
        query_embedding: List[float],
        query_text: str,
        where: Optional[Dict] = None,
    ) -> List[RetrievedDocument]:
        """
        Execute a similarity search and return ranked ``RetrievedDocument`` objects.

        Args:
            query_embedding: L2-normalised query vector (same dim as stored docs).
            query_text:       Preprocessed query string.  Stored on each result
                              so Phase 6 can build prompts without extra parameters.
            where:            Optional ChromaDB where-clause dict from
                              ``MetadataFilter.build()``.  Pass ``None`` for
                              unrestricted search.

        Returns:
            List of ``RetrievedDocument`` ordered by descending similarity score
            (most similar first).  May be empty if no results pass the threshold.

        Raises:
            SimilaritySearchError: If the ChromaDB query fails.
            RetrievalError:        If the collection cannot be opened.
        """
        collection = self._get_collection()

        # Guard: empty collection returns nothing
        try:
            doc_count = collection.count()
        except Exception as exc:
            raise SimilaritySearchError(
                f"Failed to count documents in collection: {exc}"
            ) from exc

        if doc_count == 0:
            logger.info(
                "SimilaritySearch: collection '%s' is empty — returning [].",
                self._config.collection_name,
            )
            return []

        # Clamp n_results to available documents
        n_results = min(self._config.top_k, doc_count)

        # Build include list
        include = ["distances"]
        if self._config.include_documents:
            include.append("documents")
        if self._config.include_metadata:
            include.append("metadatas")

        logger.debug(
            "SimilaritySearch: querying '%s'  top_k=%d  where=%s",
            self._config.collection_name,
            n_results,
            where,
        )

        try:
            query_kwargs: Dict = {
                "query_embeddings": [query_embedding],
                "n_results": n_results,
                "include": include,
            }
            if where is not None:
                query_kwargs["where"] = where

            raw = collection.query(**query_kwargs)
        except Exception as exc:
            raise SimilaritySearchError(
                f"ChromaDB query failed: {exc}"
            ) from exc

        results = self._convert_results(raw, query_text)
        logger.info(
            "SimilaritySearch: returned %d results (threshold=%.3f).",
            len(results),
            self._config.score_threshold,
        )
        return results

    def close(self) -> None:
        """Release the ChromaDB client if it was opened by this instance."""
        if self._persistence is not None:
            self._persistence.close()
            self._persistence = None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_collection(self) -> Collection:
        """
        Return the ChromaDB collection, opening it if not already open.

        Raises:
            RetrievalError: If the persist directory does not contain the
                            expected collection.
        """
        if self._collection is not None:
            return self._collection

        # Build a minimal VectorStoreConfig to reuse StoragePersistence
        store_config = VectorStoreConfig(
            collection_name=self._config.collection_name,
            persist_directory=self._config.persist_directory,
            embedding_model=self._config.embedding_model,
        )

        try:
            self._persistence = StoragePersistence(store_config)
            client = self._persistence.initialize()
        except Exception as exc:
            raise RetrievalError(
                f"Cannot open ChromaDB at '{self._config.persist_directory}': {exc}"
            ) from exc

        # Open the collection — it must already exist from Phase 4
        try:
            self._collection = client.get_collection(
                name=self._config.collection_name
            )
        except Exception as exc:
            raise RetrievalError(
                f"Collection '{self._config.collection_name}' not found in "
                f"'{self._config.persist_directory}'.  "
                f"Run Phase 4 first to populate the collection: {exc}"
            ) from exc

        logger.debug(
            "SimilaritySearch: opened collection '%s' (%d docs).",
            self._config.collection_name,
            self._collection.count(),
        )
        return self._collection

    def _convert_results(
        self,
        raw: Dict,
        query_text: str,
    ) -> List[RetrievedDocument]:
        """
        Convert a raw ChromaDB query response into ``RetrievedDocument`` objects.

        ChromaDB returns nested lists (one outer list per query; we always send
        exactly one query vector):
          raw["ids"]       = [[id1, id2, ...]]
          raw["distances"] = [[d1, d2, ...]]
          raw["documents"] = [[text1, text2, ...]]    (if requested)
          raw["metadatas"] = [[meta1, meta2, ...]]    (if requested)

        Args:
            raw:        ChromaDB query result dict.
            query_text: Preprocessed query string to attach to each result.

        Returns:
            Filtered, ranked list of ``RetrievedDocument`` objects.
        """
        ids       = raw.get("ids", [[]])[0]
        distances = raw.get("distances", [[]])[0]
        documents = raw.get("documents", [[None] * len(ids)])[0]
        metadatas = raw.get("metadatas", [[{}] * len(ids)])[0]

        results: List[RetrievedDocument] = []
        rank = 1

        for doc_id, distance, text, metadata in zip(ids, distances, documents, metadatas):
            # Convert distance to similarity score
            similarity = self._distance_to_similarity(float(distance))

            # Determine if this result is low confidence.
            # Uses LOW_CONFIDENCE_THRESHOLD (0.40) from config/snippet_config.py —
            # single source of truth.  Boundary: similarity == 0.40 → NOT low-confidence
            # (strictly less than).
            is_low_confidence = similarity < LOW_CONFIDENCE_THRESHOLD
            if is_low_confidence:
                logger.debug(
                    "Flagging result id=%r as low confidence (score=%.4f < threshold=%.4f)",
                    doc_id,
                    similarity,
                    LOW_CONFIDENCE_THRESHOLD,
                )

            # Apply hard filtering based on the configured score threshold.
            if similarity < self._config.score_threshold:
                logger.debug(
                    "Dropping result id=%r (score=%.4f < config threshold=%.4f)",
                    doc_id,
                    similarity,
                    self._config.score_threshold,
                )
                continue

            # Ensure text is never None (shouldn't happen, but guard defensively)
            result_text = text if text is not None else ""
            if not result_text.strip():
                logger.debug("Skipping result id=%r with empty text.", doc_id)
                continue

            results.append(
                RetrievedDocument(
                    document_id=str(doc_id),
                    text=result_text,
                    metadata=dict(metadata) if metadata else {},
                    distance=float(distance),
                    similarity_score=similarity,
                    rank=rank,
                    source_collection=self._config.collection_name,
                    query=query_text,
                    is_low_confidence=is_low_confidence,
                )
            )
            rank += 1

        return results

    def _distance_to_similarity(self, distance: float) -> float:
        """
        Convert a ChromaDB distance value to a [0, 1] similarity score.

        Conversion formulas:
          cosine : similarity = clamp(1 - distance, 0, 1)
          l2     : similarity = 1 / (1 + distance)
          ip     : similarity = clamp(distance, 0, 1)

        Args:
            distance: Raw ChromaDB distance value (>= 0).

        Returns:
            Similarity score in [0.0, 1.0].
        """
        metric = self._config.distance_metric

        if metric == "cosine":
            raw = 1.0 - distance
        elif metric == "l2":
            raw = 1.0 / (1.0 + distance)
        else:  # "ip" — inner product (pre-normalised ≈ cosine)
            raw = distance

        # Clamp to [0, 1] to handle floating-point edge cases
        return max(0.0, min(1.0, raw))
