"""
models/retrieved_document.py — Immutable model for a single retrieval result.

WHY THIS MODEL EXISTS
---------------------
``EmbeddedDocument`` represents a stored vector. ``RetrievedDocument``
represents the *result of a query* against that store — it carries
everything the caller needs to understand what was found and why:

  • The document text and metadata (what was found)
  • The distance and similarity score (how well it matched)
  • The rank within the result set (where it placed)
  • The originating query (why it was returned)
  • The source collection (which knowledge base it came from)

This separation is deliberate:
  • Phase 4 stores; Phase 5 retrieves.  The output types differ.
  • Phase 6 (RAG) will consume ``List[RetrievedDocument]`` and needs the
    query string and rank to build a coherent prompt.
  • Callers can inspect similarity_score to decide whether a result is
    relevant without re-reading any external state.

FROZEN DATACLASS
----------------
Results must never be mutated after retrieval — a pipeline stage that
reorders or rescores results should produce a new list, not mutate the
existing objects.  ``frozen=True`` enforces this.

DISTANCE vs SIMILARITY_SCORE
-----------------------------
ChromaDB returns raw distances (lower = more similar for cosine/l2).
``similarity_score`` is a normalised [0, 1] value where 1.0 = perfect
match. The conversion is performed by ``SimilaritySearch`` before this
model is constructed.  This model stores both to allow downstream callers
to use whichever representation is more natural for their use case.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievedDocument:
    """
    A single document returned by the Phase 5 retrieval pipeline.

    Attributes
    ----------
    document_id : str
        The primary key of the retrieved document, matching
        ``EmbeddedDocument.document_id`` stored in Phase 4.

    text : str
        The full text content of the retrieved chunk.

    metadata : dict
        The metadata dict as stored in ChromaDB.  Contains all Phase 2
        enrichment fields (message_count, participants, timestamps, etc.)
        and Phase 3 embedding provenance (embedding_model, schema_version).

    distance : float
        The raw distance value returned by ChromaDB.
        Lower values indicate higher similarity for cosine and l2 metrics.
        Must be >= 0.

    similarity_score : float
        Normalised similarity in [0.0, 1.0].  1.0 = perfect match.
        Derived from ``distance`` by ``SimilaritySearch``.

    rank : int
        1-based position of this result in the ranked result list.
        Rank 1 is the most similar document.

    source_collection : str
        Name of the ChromaDB collection this document was retrieved from.

    query : str
        The (preprocessed) query string that produced this result.
        Stored here so Phase 6 (RAG) can build prompts without carrying
        the query as a separate parameter.
    """

    document_id: str
    text: str
    metadata: dict
    distance: float
    similarity_score: float
    rank: int
    source_collection: str
    query: str

    # Phase 5B — query-focused snippet fields (all optional, backward-compatible)
    focused_snippet: Optional[str] = None
    matched_messages: Optional[List[Dict[str, Any]]] = None
    matched_terms: Optional[List[str]] = None
    relevance_reason: Optional[str] = None
    is_low_confidence: bool = False
    no_strong_passage: Optional[bool] = None

    # Telegram / source-identity fields (all optional — Req 11)
    # Populated from VectorMetadata when the chunk was ingested via Telegram.
    # None for chunks from other sources — backward-compatible.
    owner_id: Optional[str] = None
    source: Optional[str] = None
    source_account_id: Optional[str] = None
    conversation_id: Optional[str] = None
    conversation_title: Optional[str] = None
    conversation_type: Optional[str] = None
    sender_id: Optional[str] = None
    sender_name: Optional[str] = None
    source_message_id: Optional[str] = None
    content_type: Optional[str] = None
    timestamp: Optional[str] = None   # ISO-8601 string from metadata
    filename: Optional[str] = None
    mime_type: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate all field invariants immediately after construction."""

        # document_id
        if not isinstance(self.document_id, str) or not self.document_id.strip():
            raise ValueError("RetrievedDocument.document_id must be a non-empty string.")

        # text
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("RetrievedDocument.text must be a non-empty string.")

        # metadata
        if not isinstance(self.metadata, dict):
            raise TypeError("RetrievedDocument.metadata must be a dict.")

        # distance
        if not isinstance(self.distance, (int, float)):
            raise TypeError("RetrievedDocument.distance must be a float.")

        DISTANCE_EPSILON = 1e-8
        distance_val = float(self.distance)

        import math
        if math.isnan(distance_val) or math.isinf(distance_val):
            raise ValueError(
                f"RetrievedDocument.distance must be finite, got {distance_val!r}."
            )

        if -DISTANCE_EPSILON <= distance_val < 0.0:
            distance_val = 0.0
            object.__setattr__(self, "distance", distance_val)

        if distance_val < 0:
            raise ValueError(
                f"RetrievedDocument.distance must be >= 0, got {distance_val!r}."
            )

        # similarity_score
        if not isinstance(self.similarity_score, (int, float)):
            raise TypeError("RetrievedDocument.similarity_score must be a float.")
        if not (0.0 <= self.similarity_score <= 1.0):
            raise ValueError(
                f"RetrievedDocument.similarity_score must be in [0.0, 1.0], "
                f"got {self.similarity_score!r}."
            )

        # rank
        if not isinstance(self.rank, int) or self.rank < 1:
            raise ValueError(
                f"RetrievedDocument.rank must be a positive integer >= 1, "
                f"got {self.rank!r}."
            )

        # source_collection
        if not isinstance(self.source_collection, str) or not self.source_collection.strip():
            raise ValueError(
                "RetrievedDocument.source_collection must be a non-empty string."
            )

        # query
        if not isinstance(self.query, str):
            raise TypeError("RetrievedDocument.query must be a str.")

    def __repr__(self) -> str:
        return (
            f"RetrievedDocument("
            f"rank={self.rank}, "
            f"score={self.similarity_score:.4f}, "
            f"id={self.document_id!r}, "
            f"text={self.text[:60]!r}{'...' if len(self.text) > 60 else ''})"
        )
