"""
app/retrieval/query_embedder.py — Converts a query string into an embedding vector.

WHY THIS MODULE EXISTS
----------------------
Query embedding must use exactly the same model and normalisation as the
document embedding performed in Phase 3.  If a different model or a
different normalisation strategy were used for the query, the dot product
between the query vector and stored document vectors would be meaningless.

``QueryEmbedder`` reuses ``EmbeddingModel`` from Phase 3 directly.  It:
  • Never loads a second model instance (the singleton is reused).
  • Always normalises to unit L2 norm (``normalize_embeddings=True``).
  • Wraps Phase 3 exceptions in ``QueryEmbeddingError`` so that callers
    of the retrieval pipeline never need to import from the vectorization
    layer.

WHY LAZY IMPORT OF EmbeddingModel
----------------------------------
``sentence_transformers`` + TensorFlow take ~30 seconds to import on some
machines.  Importing ``EmbeddingModel`` at module top level would cause
every test collection run to pay that cost even when the test injects a
``FakeQueryEmbedder``.  The lazy import inside ``_get_model()`` ensures the
real model code is only loaded when a real ``QueryEmbedder`` actually
calls ``embed()``.

WHY NOT CALL model.embed_text() DIRECTLY IN THE PIPELINE
---------------------------------------------------------
Wrapping the call in a dedicated class makes the embedder mockable in
tests.  The retrieval pipeline accepts any object with an ``embed()``
method — tests can inject a ``FakeQueryEmbedder`` that returns a
deterministic fake vector without loading the real model.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import List, Optional, TYPE_CHECKING

from exceptions.exceptions import (
    QueryEmbeddingError,
    EmbeddingGenerationError,
    EmbeddingModelError,
)

# TYPE_CHECKING guard: imported only for static analysis, never at runtime
if TYPE_CHECKING:
    from app.vectorization.embedding_model import EmbeddingModel

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_NAME: str = "BAAI/bge-m3"
_BGE_M3_DIM: int = 1024


class IQueryEmbedder(ABC):
    """
    Interface for query embedders.

    Decouples the retrieval pipeline from the concrete embedding
    implementation, enabling test doubles without touching model weights.
    """

    @abstractmethod
    def embed(self, query: str) -> List[float]:
        """
        Convert a cleaned query string into an L2-normalised embedding vector.

        Args:
            query: Preprocessed, non-empty query string.

        Returns:
            ``list[float]`` with L2 norm ≈ 1.0.

        Raises:
            QueryEmbeddingError: If embedding fails for any reason.
        """


class QueryEmbedder(IQueryEmbedder):
    """
    Production query embedder backed by ``EmbeddingModel`` (BGE-M3 singleton).

    The ``EmbeddingModel`` is imported and instantiated lazily on the
    first call to ``embed()`` — not at construction time — so that
    importing this module in tests does not trigger the full
    SentenceTransformers import chain.

    Parameters
    ----------
    model_name : str
        HuggingFace model identifier.  Defaults to ``"BAAI/bge-m3"``.

    Usage
    -----
    ::

        embedder = QueryEmbedder()
        vector = embedder.embed("What did Alice say about the project?")
        # list[float], len=1024, ||v||2 ~= 1.0
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL_NAME) -> None:
        self._model_name = model_name
        self._model: Optional["EmbeddingModel"] = None  # lazy-loaded

    def embed(self, query: str) -> List[float]:
        """
        Embed a query using the BGE-M3 model.

        Delegates to ``EmbeddingModel.embed_text()`` and wraps any raised
        exception in ``QueryEmbeddingError``.

        Args:
            query: Preprocessed, non-empty query string.

        Returns:
            ``list[float]`` with L2 norm ~= 1.0 and length == 1024.

        Raises:
            QueryEmbeddingError: On any embedding failure.
        """
        if not query or not query.strip():
            raise QueryEmbeddingError(
                "QueryEmbedder received an empty query string.  "
                "Run QueryPreprocessor.preprocess() before calling embed()."
            )

        logger.debug("Embedding query (first 80 chars): %r", query[:80])

        model = self._get_model()

        try:
            vector = model.embed_text(query)
        except (EmbeddingGenerationError, EmbeddingModelError) as exc:
            raise QueryEmbeddingError(
                f"Failed to embed query: {exc}"
            ) from exc
        except Exception as exc:
            raise QueryEmbeddingError(
                f"Unexpected error while embedding query: {exc}"
            ) from exc

        logger.debug("Query embedded successfully.  dim=%d", len(vector))
        return vector

    @property
    def embedding_dim(self) -> int:
        """The dimension of vectors produced by this embedder."""
        if self._model is not None:
            return self._model.embedding_dim
        # Return known constant without loading the model
        return _BGE_M3_DIM

    def _get_model(self) -> "EmbeddingModel":
        """
        Lazy-load and return the EmbeddingModel singleton.

        The deferred import means that merely importing ``query_embedder``
        does not pull in ``sentence_transformers`` — only calling ``embed()``
        does.
        """
        if self._model is None:
            from app.vectorization.embedding_model import EmbeddingModel
            self._model = EmbeddingModel(self._model_name)
        return self._model
