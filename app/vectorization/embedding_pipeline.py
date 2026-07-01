"""
app/vectorization/embedding_pipeline.py — Phase 3 orchestrator.

WHY THIS MODULE EXISTS
----------------------
Each Phase 3 sub-component has a single responsibility:

  • ``EmbeddingModel``     — load the model and produce vectors
  • ``EmbeddingCache``     — avoid re-embedding duplicate texts
  • ``EmbeddingGenerator`` — convert one Document → EmbeddedDocument
  • ``EmbeddingBatcher``   — process a list of Documents efficiently

``EmbeddingPipeline`` wires them together, provides sensible defaults, and
exposes one clean entry point:

    embedded_docs = EmbeddingPipeline(documents).run()

DEPENDENCY INJECTION
--------------------
Every collaborator (model, cache, batcher) is injected via the constructor.
This is essential for:

  • **Testability** — unit tests can inject a mock model that returns
    deterministic fake vectors without loading 570 MB of weights.
  • **Flexibility** — future phases can swap in a different model
    (e.g. ``BAAI/bge-large-en-v1.5``) by passing a different ``EmbeddingModel``.
  • **Configurability** — batch size and cache size are tunable per
    deployment without subclassing.

HOW THIS PREPARES PHASE 4
--------------------------
Phase 4 will store ``EmbeddedDocument`` objects in a vector database
(FAISS / Chroma / Qdrant).  The ``EmbeddedDocument`` model is designed to
map directly to the schema of these databases:

  • ``document_id``    → primary key / payload ID
  • ``embedding``      → the dense vector to index
  • ``text``           → payload field for hybrid retrieval
  • ``metadata``       → payload fields for filtered retrieval
  • ``model_name``     → collection-level schema validation
  • ``embedding_dim``  → index dimensionality check

No changes to ``EmbeddedDocument`` should be needed for Phase 4.
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional

from models.document import Document
from models.embedded_document import EmbeddedDocument
from app.vectorization.embedding_model import EmbeddingModel, DEFAULT_MODEL_NAME
from app.vectorization.embedding_cache import EmbeddingCache
from app.vectorization.embedding_batcher import EmbeddingBatcher, DEFAULT_BATCH_SIZE
from exceptions.exceptions import EmbeddingModelError, EmbeddingGenerationError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sentinel object used to distinguish "cache not passed" from "cache=None"
# ---------------------------------------------------------------------------
_CACHE_NOT_SET = object()


class EmbeddingPipeline:
    """
    Orchestrates the conversion of ``List[Document]`` → ``List[EmbeddedDocument]``.

    Parameters
    ----------
    documents : List[Document]
        Output of ``Phase2Pipeline.run()``.

    model : EmbeddingModel, optional
        Embedding model to use.  Defaults to the singleton
        ``EmbeddingModel("BAAI/bge-m3")``.  Inject a mock in tests.

    cache : EmbeddingCache or None, optional
        Embedding cache.  When not supplied, a default
        ``EmbeddingCache(max_size=10_000)`` is created automatically.
        Pass ``None`` explicitly to disable caching entirely.

    batch_size : int
        Documents per model inference call.  Default: 32.

    Example
    -------
    ::

        # End-to-end usage
        from pipeline.phase1_pipeline import Phase1Pipeline
        from app.documents.phase2_pipeline import Phase2Pipeline
        from app.vectorization.embedding_pipeline import EmbeddingPipeline

        chat      = Phase1Pipeline("export.zip").run()
        documents = Phase2Pipeline(chat).run()
        embedded  = EmbeddingPipeline(documents).run()
        # embedded is List[EmbeddedDocument]

        # With custom configuration
        from app.vectorization.embedding_model import EmbeddingModel
        from app.vectorization.embedding_cache import EmbeddingCache

        model    = EmbeddingModel("BAAI/bge-m3")
        cache    = EmbeddingCache(max_size=50_000)
        embedded = EmbeddingPipeline(
            documents, model=model, cache=cache, batch_size=64
        ).run()
    """

    def __init__(
        self,
        documents: List[Document],
        model: Optional[EmbeddingModel] = None,
        cache: object = _CACHE_NOT_SET,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        if not isinstance(documents, list):
            raise TypeError(
                f"EmbeddingPipeline expects a list of Documents, "
                f"got {type(documents).__name__}."
            )
        # Validate that list members are Documents (sample-check first item)
        if documents and not isinstance(documents[0], Document):
            raise TypeError(
                f"EmbeddingPipeline expects List[Document], "
                f"but first element is {type(documents[0]).__name__}."
            )

        self._documents = documents

        # Model: use provided or fall back to singleton
        self._model: EmbeddingModel = model or EmbeddingModel(DEFAULT_MODEL_NAME)

        # Cache: sentinel means "not supplied → use default".
        # Explicit None means "disable caching".
        if cache is _CACHE_NOT_SET:
            self._cache: Optional[EmbeddingCache] = EmbeddingCache()
        else:
            self._cache = cache  # type: ignore[assignment]

        self._batch_size = batch_size

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> List[EmbeddedDocument]:
        """
        Execute the full Phase 3 embedding pipeline.

        Returns:
            Ordered ``List[EmbeddedDocument]`` where each item corresponds
            to the ``Document`` at the same index in the input list.
            Returns ``[]`` when the input document list is empty.

        Raises:
            EmbeddingModelError: If the model cannot be loaded.
            EmbeddingGenerationError: If any document fails to embed.
        """
        if not self._documents:
            logger.warning("EmbeddingPipeline: no documents to embed; returning [].")
            return []

        logger.info(
            "Phase 3 pipeline starting.  Documents: %d  Model: %s  "
            "Batch size: %d  Cache: %s",
            len(self._documents),
            self._model.model_name,
            self._batch_size,
            "enabled" if self._cache is not None else "disabled",
        )

        start = time.perf_counter()

        batcher = EmbeddingBatcher(
            model=self._model,
            cache=self._cache,
            batch_size=self._batch_size,
        )
        embedded = batcher.embed_all(self._documents)

        elapsed = time.perf_counter() - start

        # Log final summary
        if embedded:
            sample_dim = embedded[0].embedding_dim
            logger.info(
                "Phase 3 pipeline complete.  "
                "EmbeddedDocuments: %d  Dim: %d  Model: %s  Elapsed: %.2fs",
                len(embedded),
                sample_dim,
                self._model.model_name,
                elapsed,
            )
            if self._cache is not None:
                stats = self._cache.stats()
                logger.info(
                    "Cache stats — hits: %d  misses: %d  "
                    "hit_rate: %.1f%%  size: %d",
                    stats["hits"],
                    stats["misses"],
                    stats["hit_rate"] * 100,
                    stats["size"],
                )

        return embedded
