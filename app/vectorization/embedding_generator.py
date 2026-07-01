"""
app/vectorization/embedding_generator.py — Single-document embedding generator.

WHY THIS MODULE EXISTS
----------------------
The ``EmbeddingModel`` knows how to produce vectors.
The ``EmbeddingCache`` knows how to store and retrieve them.
Neither knows about ``Document`` or ``EmbeddedDocument``.

``EmbeddingGenerator`` is the adapter that:
  1. Accepts a ``Document`` (Phase 2 output)
  2. Checks the cache for an existing embedding
  3. Calls the model if there is a cache miss
  4. Validates the resulting vector
  5. Constructs and returns an ``EmbeddedDocument`` (Phase 3 output)

All metadata, participants, timestamps, and token counts from the source
``Document`` are preserved verbatim.  Phase 3 adds only what it uniquely
contributes: the embedding vector, the model name, the embedding dimension,
and the creation timestamp.

NEVER MUTATE DOCUMENTS
-----------------------
``Document`` is frozen.  ``EmbeddedDocument`` is frozen.  The generator
creates, never modifies.  This makes the pipeline referentially transparent:
the same input always produces the same output (given the same model).
"""

from __future__ import annotations

import logging
import math
from typing import Optional

from models.document import Document
from models.embedded_document import EmbeddedDocument, embedding_to_tuple, utc_now_iso
from app.vectorization.embedding_model import EmbeddingModel
from app.vectorization.embedding_cache import EmbeddingCache
from exceptions.exceptions import EmbeddingGenerationError, EmbeddingValidationError

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """
    Converts a single ``Document`` into an ``EmbeddedDocument``.

    Parameters
    ----------
    model : EmbeddingModel
        The loaded (or lazy-loading) embedding model.  Injected so tests
        can substitute a mock without loading real model weights.
    cache : EmbeddingCache, optional
        When supplied, embeddings are looked up and stored in the cache.
        Pass ``None`` to disable caching entirely.
    """

    def __init__(
        self,
        model: EmbeddingModel,
        cache: Optional[EmbeddingCache] = None,
    ) -> None:
        if not isinstance(model, EmbeddingModel):
            raise TypeError(
                f"EmbeddingGenerator requires an EmbeddingModel, "
                f"got {type(model).__name__}."
            )
        self._model = model
        self._cache = cache

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, document: Document) -> EmbeddedDocument:
        """
        Produce an ``EmbeddedDocument`` for the given ``Document``.

        Steps:
        1. If cache is enabled: compute the cache key and check for a hit.
        2. On cache miss (or no cache): call ``model.embed_text()``.
        3. Validate the resulting vector.
        4. Store in cache if enabled.
        5. Construct and return ``EmbeddedDocument``.

        Args:
            document: A fully populated ``Document`` from Phase 2.

        Returns:
            An ``EmbeddedDocument`` with the L2-normalised embedding.

        Raises:
            EmbeddingGenerationError: If the model fails to produce a vector.
            EmbeddingValidationError: If the vector fails post-generation
                                      validation checks.
        """
        if not isinstance(document, Document):
            raise EmbeddingGenerationError(
                f"Expected Document, got {type(document).__name__}."
            )

        text = document.text
        cache_key: Optional[str] = None

        # ── Cache lookup ─────────────────────────────────────────────
        if self._cache is not None:
            cache_key = self._cache.compute_key(text)
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug(
                    "Cache HIT for document_id=%s (key=%s…)",
                    document.id,
                    cache_key[:12],
                )
                return self._build_embedded_document(document, cached)

        # ── Model inference ──────────────────────────────────────────
        logger.debug(
            "Cache MISS for document_id=%s — calling model.", document.id
        )

        # Handle empty-text documents gracefully: use a single zero dimension
        # with a sentinel vector.  This should be rare (system-message-only
        # chunks) but must not crash the pipeline.
        if not text or not text.strip():
            logger.warning(
                "Document id=%s has empty text; using zero-vector sentinel.",
                document.id,
            )
            dim = self._model.embedding_dim
            embedding: list = [0.0] * dim
            # Zero-vector sentinel bypasses norm validation — it is a known
            # placeholder, not a real embedding.  Store in cache so subsequent
            # calls for the same empty document resolve instantly.
            if self._cache is not None and cache_key is not None:
                self._cache.put(cache_key, embedding)
            return self._build_embedded_document(document, embedding)

        embedding = self._model.embed_text(text)

        # ── Validation ──────────────────────────────────────────────
        self._validate_vector(embedding, document.id)

        # ── Cache store ──────────────────────────────────────────────
        if self._cache is not None and cache_key is not None:
            self._cache.put(cache_key, embedding)

        return self._build_embedded_document(document, embedding)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_embedded_document(
        self,
        document: Document,
        embedding: list,
    ) -> EmbeddedDocument:
        """
        Construct an ``EmbeddedDocument`` from *document* and *embedding*.

        The metadata dict is extended (not replaced) with embedding-specific
        keys so that all Phase 2 metadata is preserved.

        Args:
            document: Source document.
            embedding: The embedding vector as a ``list[float]``.

        Returns:
            A frozen ``EmbeddedDocument`` instance.
        """
        # Extend — not replace — the metadata dict
        extended_metadata = {
            **document.metadata,
            "embedding_model": self._model.model_name,
            "embedding_dim": len(embedding),
            "participants": list(document.participants),
            "attachments": list(document.attachments),
            "message_ids": list(document.message_ids),
            "source_chat": document.source_chat,
            "chunk_index": document.chunk_index,
            "start_timestamp": document.start_timestamp,
            "end_timestamp": document.end_timestamp,
        }

        return EmbeddedDocument(
            document_id=document.id,
            text=document.text,
            embedding=embedding_to_tuple(embedding),
            metadata=extended_metadata,
            token_count=document.token_count,
            model_name=self._model.model_name,
            embedding_dim=len(embedding),
            created_at=utc_now_iso(),
        )

    @staticmethod
    def _validate_vector(embedding: list, document_id: str) -> None:
        """
        Validate that *embedding* is a non-empty list of finite floats.

        Checks:
          • Non-empty
          • All values are finite (no NaN, no Inf)
          • Vector has non-zero norm (prevents division-by-zero in cosine sim)

        Args:
            embedding: The vector to validate.
            document_id: Used in error messages for traceability.

        Raises:
            EmbeddingValidationError: If any check fails.
        """
        if not embedding:
            raise EmbeddingValidationError(
                f"Model returned empty embedding for document_id={document_id}."
            )

        norm_sq = 0.0
        for i, v in enumerate(embedding):
            if math.isnan(v) or math.isinf(v):
                raise EmbeddingValidationError(
                    f"Embedding for document_id={document_id} contains "
                    f"NaN or Inf at index {i}."
                )
            norm_sq += v * v

        if norm_sq == 0.0:
            raise EmbeddingValidationError(
                f"Embedding for document_id={document_id} has zero norm.  "
                "The document may consist entirely of unknown tokens."
            )
