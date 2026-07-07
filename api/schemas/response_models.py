"""
api/schemas/response_models.py — Pydantic v2 response models for Phase 7.

Every API response is typed with an explicit model — no bare ``dict`` or
``Any`` unless genuinely unavoidable.  All sensitive data (absolute paths,
API keys, full chat text) is excluded.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Error response (used by all failure paths)
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    """
    Uniform error envelope returned for all HTTP 4xx/5xx responses.

    Attributes
    ----------
    error : str
        Short machine-readable error code (e.g. ``"invalid_input"``).
    message : str
        Human-readable description safe to show to the client.  Never
        contains stack traces, absolute paths, or secrets.
    detail : str | None
        Optional additional context.  Still client-safe.
    """

    error: str = Field(..., description="Short error code.")
    message: str = Field(..., description="Human-readable error description.")
    detail: Optional[str] = Field(default=None, description="Optional extra detail.")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    """
    Response body for ``GET /health``.

    Attributes
    ----------
    status : str
        ``"ok"`` when all components are healthy, ``"degraded"`` when the
        LLM provider is unreachable (non-fatal).
    app_name : str
        Application name.
    version : str
        API semantic version string.
    engine_status : str
        ``"ok"`` if all Phase 1-6 modules imported successfully.
    llm_provider_available : bool
        Result of a lightweight, non-blocking availability probe.
    """

    status: str = Field(..., description='"ok" or "degraded".')
    app_name: str = Field(..., description="Application name.")
    version: str = Field(..., description="API version.")
    engine_status: str = Field(..., description='"ok" if engine imports succeeded.')
    llm_provider_available: bool = Field(
        ..., description="Whether the LLM provider is reachable."
    )


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

class PhaseStatus(BaseModel):
    """Per-phase processing status included in UploadResponse."""

    phase: str = Field(..., description="Phase identifier, e.g. 'phase1'.")
    status: str = Field(..., description='"success" or "failed".')
    detail: Optional[str] = Field(default=None, description="Optional detail.")


class UploadResponse(BaseModel):
    """
    Response body for ``POST /upload``.

    Attributes
    ----------
    collection_name : str
        Generated collection name (never the raw client filename).
    messages_parsed : int
        Number of messages parsed by Phase 1.
    chunks_created : int
        Number of document chunks produced by Phase 2.
    vectors_indexed : int
        Number of vectors written to ChromaDB by Phase 4.
    phase_statuses : list[PhaseStatus]
        Per-phase success/failure summary.
    elapsed_seconds : float
        Total wall-clock processing time in seconds.
    """

    collection_name: str = Field(..., description="Generated collection identifier.")
    messages_parsed: int = Field(..., description="Messages parsed by Phase 1.")
    chunks_created: int = Field(..., description="Document chunks from Phase 2.")
    vectors_indexed: int = Field(..., description="Vectors written to ChromaDB.")
    phase_statuses: List[PhaseStatus] = Field(
        default_factory=list,
        description="Per-phase success/failure summary.",
    )
    elapsed_seconds: float = Field(..., description="Total processing time (seconds).")


# ---------------------------------------------------------------------------
# Query / retrieval
# ---------------------------------------------------------------------------

class CitationResponse(BaseModel):
    """
    A single citation record returned with a RAG answer.

    Attributes
    ----------
    document_id : str
        ID of the retrieved document chunk.
    rank : int
        Retrieval rank (1-based, lower = more similar).
    similarity_score : float
        Cosine similarity in [0, 1].
    source_chat : str
        Originating chat label.
    chunk_index : int
        Zero-based chunk position within the source chat.
    start_timestamp : str
        Timestamp of the first message in the chunk.
    end_timestamp : str
        Timestamp of the last message in the chunk.
    """

    document_id: str = Field(..., description="Chunk document ID.")
    rank: int = Field(..., description="Retrieval rank (1-based).")
    similarity_score: float = Field(..., description="Similarity score [0, 1].")
    source_chat: str = Field(..., description="Originating chat label.")
    chunk_index: int = Field(..., description="Zero-based chunk position.")
    start_timestamp: str = Field(..., description="First message timestamp.")
    end_timestamp: str = Field(..., description="Last message timestamp.")


class RetrievedDocumentResponse(BaseModel):
    """
    A single retrieved document chunk as returned to the API client.

    Attributes
    ----------
    document_id : str
        Chunk identifier.
    text : str
        Document text content.
    similarity_score : float
        Cosine similarity in [0, 1].
    rank : int
        Retrieval rank (1-based).
    metadata : dict
        Enriched metadata from Phases 2-3 (media flags, timestamps, etc.).
    """

    document_id: str = Field(..., description="Chunk identifier.")
    text: str = Field(..., description="Document text content.")
    similarity_score: float = Field(..., description="Similarity score [0, 1].")
    rank: int = Field(..., description="Retrieval rank (1-based).")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Enriched chunk metadata."
    )


class QueryResponse(BaseModel):
    """
    Response body for ``POST /query``.

    Attributes
    ----------
    question : str
        The (pre-processed) question that was answered.
    answer : str | None
        Grounded answer from Phase 6, or ``None`` when RAG was skipped or
        the LLM was unavailable.
    citations : list[CitationResponse]
        Provenance records for the answer (empty when ``answer`` is ``None``).
    retrieved_documents : list[RetrievedDocumentResponse]
        All retrieved document chunks, always present.
    confidence : float | None
        Mean retrieval similarity across cited documents, or ``None``
        when no RAG answer was produced.
    llm_used : bool
        Whether Phase 6 was executed successfully.
    message : str | None
        Informational message, e.g. "LLM unavailable; retrieval-only results."
    elapsed_seconds : float
        Total query processing time.
    """

    question: str = Field(..., description="The answered question.")
    answer: Optional[str] = Field(
        default=None, description="Grounded answer, or null if RAG was skipped."
    )
    citations: List[CitationResponse] = Field(
        default_factory=list, description="Provenance citations for the answer."
    )
    retrieved_documents: List[RetrievedDocumentResponse] = Field(
        default_factory=list, description="All retrieved document chunks."
    )
    confidence: Optional[float] = Field(
        default=None, description="Mean retrieval similarity (0-1), or null."
    )
    llm_used: bool = Field(
        default=False, description="Whether Phase 6 RAG was executed."
    )
    message: Optional[str] = Field(
        default=None, description="Informational note, e.g. LLM unavailability."
    )
    elapsed_seconds: float = Field(..., description="Total query time (seconds).")


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------

class CollectionInfo(BaseModel):
    """
    Metadata for a single indexed collection.

    Attributes
    ----------
    name : str
        Collection name.
    document_count : int
        Number of vectors/documents in the collection.
    embedding_model : str
        The embedding model used to create this collection.
    schema_version : str
        Storage schema version.
    """

    name: str = Field(..., description="Collection name.")
    document_count: int = Field(..., description="Number of indexed document chunks.")
    embedding_model: str = Field(..., description="Embedding model identifier.")
    schema_version: str = Field(..., description="Storage schema version.")


class CollectionListResponse(BaseModel):
    """
    Response body for ``GET /collections``.

    Attributes
    ----------
    collections : list[CollectionInfo]
        All known collections (may be empty).
    total : int
        Total number of collections.
    """

    collections: List[CollectionInfo] = Field(
        default_factory=list, description="List of indexed collections."
    )
    total: int = Field(..., description="Total collection count.")


class DeleteCollectionResponse(BaseModel):
    """
    Response body for ``DELETE /collections/{collection_name}``.

    Attributes
    ----------
    collection_name : str
        The name of the deleted collection.
    deleted : bool
        ``True`` if deletion succeeded completely.
    message : str
        Human-readable confirmation or partial-failure description.
    """

    collection_name: str = Field(..., description="Name of the deleted collection.")
    deleted: bool = Field(..., description="Whether deletion succeeded.")
    message: str = Field(..., description="Confirmation or error detail.")
