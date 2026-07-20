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

class SecretStoreHealthResponse(BaseModel):
    """Safe secret-store health info — no key material, no plaintext."""
    status: str = Field(..., description='"healthy", "degraded", or "unavailable".')
    provider: str = Field(..., description="Provider name.")
    encryption_version: str = Field(..., description="Payload version.")
    key_id: Optional[str] = Field(default=None, description="Active key identifier.")
    message: Optional[str] = Field(default=None, description="Optional diagnostic note.")


class HealthResponse(BaseModel):
    """Response body for ``GET /health``."""
    status: str = Field(..., description='"ok" or "degraded".')
    app_name: str = Field(..., description="Application name.")
    version: str = Field(..., description="API version.")
    engine_status: str = Field(..., description='"ok" if engine imports succeeded.')
    llm_provider_available: bool = Field(
        ..., description="Whether the LLM provider is reachable."
    )
    secret_store: Optional[SecretStoreHealthResponse] = Field(
        default=None, description="Secret-store health. None when not yet probed."
    )


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
    focused_snippet: Optional[str] = Field(
        default=None, description="Extracted query-focused lines from the chunk."
    )
    matched_messages: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Verbatim matched messages from the chunk (each has 'text' and 'index')."
    )
    matched_terms: Optional[List[str]] = Field(
        default=None, description="Query terms that produced exact or partial matches."
    )
    relevance_reason: Optional[str] = Field(
        default=None, description="Template-built explanation for why this chunk was matched."
    )
    is_low_confidence: bool = Field(
        default=False, description="True if similarity score is below the low-confidence threshold."
    )
    no_strong_passage: Optional[bool] = Field(
        default=None, description="True if no messages in this chunk matched any query term."
    )
    # Telegram / source-identity fields [ADDITIVE — Req 11]
    owner_id: Optional[str] = Field(default=None, description="Owner of this chunk.")
    source: Optional[str] = Field(default=None, description="Source platform (e.g. 'telegram').")
    source_account_id: Optional[str] = Field(default=None)
    conversation_id: Optional[str] = Field(default=None)
    conversation_title: Optional[str] = Field(default=None)
    conversation_type: Optional[str] = Field(default=None)
    sender_id: Optional[str] = Field(default=None, description="Stable sender identifier.")
    sender_name: Optional[str] = Field(default=None, description="Display name only.")
    source_message_id: Optional[str] = Field(default=None)
    content_type: Optional[str] = Field(default=None)
    timestamp: Optional[str] = Field(default=None, description="ISO-8601 message timestamp.")
    filename: Optional[str] = Field(default=None)
    mime_type: Optional[str] = Field(default=None)


class TelegramSourceResponse(BaseModel):
    """
    A single Telegram source citation included in the RAG query response.

    All fields are optional — non-Telegram sources simply omit them.
    Internal paths, phone numbers, and session details are NEVER included.

    Requirement: 12, 14.
    """

    document_id: str = Field(..., description="Chunk vector document ID.")
    source: str = Field(default="telegram", description="Source platform.")
    conversation_id: str = Field(default="", description="Stable conversation identifier.")
    conversation_title: str = Field(default="", description="Human-readable chat title.")
    conversation_type: str = Field(default="", description="private / group / channel.")
    sender_id: str = Field(default="", description="Stable sender identifier (not display name).")
    sender_name: str = Field(default="", description="Display name (presentation only).")
    message_id: str = Field(default="", description="Original Telegram message ID.")
    timestamp: str = Field(default="", description="ISO-8601 message timestamp.")
    content_type: str = Field(default="text", description="text / pdf / image / voice / etc.")
    filename: str = Field(default="", description="Attachment filename when applicable.")
    chunk_index: int = Field(default=0, description="Zero-based chunk index.")
    snippet: str = Field(default="", description="Relevant text snippet from this chunk.")
    score: float = Field(default=0.0, description="Similarity score [0, 1].")


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
    sources : list[TelegramSourceResponse]
        Telegram-native source citations (Req 12). Empty for non-Telegram or
        when no documents were retrieved. Additive — old clients can ignore it.
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
    sources: List["TelegramSourceResponse"] = Field(
        default_factory=list,
        description="Telegram-native source citations (Req 12). Empty for non-Telegram sources.",
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
    no_strong_match: bool = Field(
        default=False, description="True if no retrieved documents meet the similarity threshold."
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
