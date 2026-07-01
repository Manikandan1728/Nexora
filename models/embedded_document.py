"""
models/embedded_document.py — Immutable model for a vectorised document chunk.

WHY THIS MODEL EXISTS
---------------------
A ``Document`` produced by Phase 2 contains clean text and rich metadata,
but no vector representation.  Vector databases (FAISS, Chroma, Qdrant,
Milvus) require a numeric embedding alongside the text and metadata.

``EmbeddedDocument`` is the output contract of Phase 3.  It bundles:

  • The original ``Document.id`` for traceability back to the source chat
  • The embedding vector (L2-normalised, ready for cosine similarity)
  • The original text (needed by the vector store for hybrid search / BM25)
  • A frozen copy of the metadata dict (passed through from Phase 2)
  • Housekeeping fields (model name, dimension, creation timestamp)

DESIGN DECISIONS
----------------
``frozen=True``
    The same rationale as ``Document``: EmbeddedDocuments are write-once
    objects.  Once a vector is computed and validated, it must never change.
    Immutability prevents subtle bugs where a later pipeline stage
    accidentally overwrites an embedding.

``embedding: tuple``
    numpy arrays are mutable and cannot be stored in a frozen dataclass.
    We convert ``list[float]`` / ``np.ndarray`` to a ``tuple[float, ...]``
    at construction time.  This also makes the object trivially hashable
    and serialisable.  The trade-off is a small conversion cost, which is
    negligible compared to the cost of running the embedding model.

``metadata: dict`` (not frozen)
    Vector stores serialise metadata to JSON.  A plain ``dict`` is the
    most compatible choice.  The enrichment step (Phase 2) already
    populates it; Phase 3 adds only ``embedding_model`` and
    ``embedding_dim`` keys to avoid overwriting existing metadata.

``created_at: str``
    ISO-8601 UTC timestamp recorded at construction.  Used for cache
    invalidation, audit trails, and debugging stale embeddings.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence


@dataclass(frozen=True)
class EmbeddedDocument:
    """
    A single document chunk paired with its L2-normalised embedding vector.

    Attributes
    ----------
    document_id : str
        The ``Document.id`` of the source document.  Primary key for
        tracing an embedding back to its originating chat chunk.

    text : str
        The verbatim text that was embedded.  Stored here so vector stores
        can perform hybrid (semantic + keyword) retrieval without joining
        back to a separate document store.

    embedding : tuple[float, ...]
        The L2-normalised embedding vector produced by BAAI/bge-m3.
        All values are in [-1, 1]; the vector has unit norm (‖v‖₂ = 1).
        Stored as a ``tuple`` for immutability and hashability.

    metadata : dict
        Enriched metadata from Phase 2, extended with embedding-specific
        keys (``embedding_model``, ``embedding_dim``).  Passed through
        unchanged to the vector store.

    token_count : int
        Token count of ``text`` as measured in Phase 2.  Preserved here
        so the vector store can filter by chunk size without re-tokenizing.

    model_name : str
        Full HuggingFace model identifier used to produce this embedding
        (e.g. ``"BAAI/bge-m3"``).  Required for cache invalidation when
        the model changes between pipeline runs.

    embedding_dim : int
        Number of dimensions in the embedding vector.  Must equal
        ``len(embedding)``.  Stored explicitly for fast schema validation
        in the vector store without unpacking the full vector.

    created_at : str
        ISO-8601 UTC timestamp of when this object was created.
        Format: ``"2024-01-01T09:00:00.000000+00:00"``.
    """

    document_id: str
    text: str
    embedding: tuple
    metadata: dict
    token_count: int
    model_name: str
    embedding_dim: int
    created_at: str

    def __post_init__(self) -> None:
        """Validate all field invariants immediately after construction."""

        # --- document_id ---
        if not isinstance(self.document_id, str) or not self.document_id.strip():
            raise ValueError("EmbeddedDocument.document_id must be a non-empty string.")

        # --- text ---
        if not isinstance(self.text, str):
            raise TypeError("EmbeddedDocument.text must be a str.")

        # --- embedding ---
        if not isinstance(self.embedding, tuple):
            raise TypeError(
                "EmbeddedDocument.embedding must be a tuple.  "
                "Convert numpy arrays or lists before construction."
            )
        if len(self.embedding) == 0:
            raise ValueError("EmbeddedDocument.embedding must not be empty.")

        # Validate no NaN / Inf values — these corrupt cosine similarity
        for i, v in enumerate(self.embedding):
            if not isinstance(v, (int, float)):
                raise TypeError(
                    f"EmbeddedDocument.embedding[{i}] must be a numeric type, "
                    f"got {type(v).__name__}."
                )
            if math.isnan(v) or math.isinf(v):
                raise ValueError(
                    f"EmbeddedDocument.embedding contains NaN or Inf at index {i}."
                )

        # --- metadata ---
        if not isinstance(self.metadata, dict):
            raise TypeError("EmbeddedDocument.metadata must be a dict.")

        # --- token_count ---
        if not isinstance(self.token_count, int) or self.token_count < 0:
            raise ValueError("EmbeddedDocument.token_count must be a non-negative integer.")

        # --- model_name ---
        if not isinstance(self.model_name, str) or not self.model_name.strip():
            raise ValueError("EmbeddedDocument.model_name must be a non-empty string.")

        # --- embedding_dim ---
        if not isinstance(self.embedding_dim, int) or self.embedding_dim <= 0:
            raise ValueError("EmbeddedDocument.embedding_dim must be a positive integer.")
        if self.embedding_dim != len(self.embedding):
            raise ValueError(
                f"EmbeddedDocument.embedding_dim ({self.embedding_dim}) "
                f"does not match len(embedding) ({len(self.embedding)})."
            )

        # --- created_at ---
        if not isinstance(self.created_at, str) or not self.created_at.strip():
            raise ValueError("EmbeddedDocument.created_at must be a non-empty string.")

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @property
    def is_normalised(self) -> bool:
        """
        Return True when the embedding vector has (approximately) unit L2 norm.

        Tolerance of 1e-5 accounts for floating-point rounding across
        different hardware and BLAS implementations.
        """
        norm_sq = sum(v * v for v in self.embedding)
        return abs(norm_sq - 1.0) < 1e-4

    def __repr__(self) -> str:
        return (
            f"EmbeddedDocument("
            f"document_id={self.document_id!r}, "
            f"model={self.model_name!r}, "
            f"dim={self.embedding_dim}, "
            f"token_count={self.token_count}, "
            f"normalised={self.is_normalised})"
        )


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(tz=timezone.utc).isoformat()


def embedding_to_tuple(embedding: Sequence) -> tuple:
    """
    Convert any sequence (list, numpy ndarray, etc.) to a tuple of Python floats.

    Args:
        embedding: Any numeric sequence.

    Returns:
        Immutable tuple of Python ``float`` values.

    Raises:
        ValueError: If the resulting tuple is empty.
    """
    result = tuple(float(v) for v in embedding)
    if not result:
        raise ValueError("Cannot convert an empty sequence to an embedding tuple.")
    return result
