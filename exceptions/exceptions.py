class InvalidInputError(Exception):
    """Raised when the input is invalid."""
    def __init__(self, message: str):
        super().__init__(message)

class ParsingError(Exception):
    """
    Raised when parsing fails.
    """
    def __init__(self, message: str):
        super().__init__(message)


class TokenizationError(Exception):
    """
    Raised when the tokenizer service encounters an unrecoverable error
    (e.g. the model weights cannot be loaded, or a message cannot be
    encoded).
    """
    def __init__(self, message: str):
        super().__init__(message)


class ChunkingError(Exception):
    """
    Raised when the chunker cannot produce a valid chunk list from the
    supplied messages (e.g. empty input, or a single message whose text
    cannot be split at sentence boundaries within the token limit).
    """
    def __init__(self, message: str):
        super().__init__(message)


class DocumentBuildError(Exception):
    """
    Raised when the document builder fails to construct a Document from
    a message chunk (e.g. missing required fields, invalid timestamps).
    """
    def __init__(self, message: str):
        super().__init__(message)


class EmbeddingModelError(Exception):
    """
    Raised when the embedding model cannot be loaded or initialised.

    This covers HuggingFace download failures, CUDA OOM during model load,
    corrupted weight files, and any other unrecoverable model-level error.
    Callers should treat this as fatal — the pipeline cannot continue
    without a functioning embedding model.
    """
    def __init__(self, message: str):
        super().__init__(message)


class EmbeddingGenerationError(Exception):
    """
    Raised when the model is loaded successfully but fails to produce
    an embedding for a specific document or batch.

    Examples: NaN outputs from the model, shape mismatches, runtime
    errors during ``model.encode()``.  Unlike ``EmbeddingModelError``,
    this error may be recoverable by retrying with a smaller batch or
    a different document.
    """
    def __init__(self, message: str):
        super().__init__(message)


class EmbeddingValidationError(Exception):
    """
    Raised when an embedding vector fails post-generation validation.

    Validation checks include: empty vector, wrong dimension, presence of
    NaN or Inf values, and zero-norm vectors (which would cause division-
    by-zero during cosine similarity computation).
    """
    def __init__(self, message: str):
        super().__init__(message)


class CacheError(Exception):
    """
    Raised when the embedding cache encounters an unrecoverable internal
    error (e.g. a corrupted cache entry, hash collision, or serialisation
    failure).  Normal cache misses are NOT errors and must never raise this.
    """
    def __init__(self, message: str):
        super().__init__(message)


class VectorStoreError(Exception):
    """
    Raised when the vector store encounters an unrecoverable error.

    Covers initialisation failures, client connection errors, and any
    ChromaDB-level exception that cannot be handled gracefully.  Callers
    should treat this as fatal for the current pipeline run.
    """
    def __init__(self, message: str):
        super().__init__(message)


class CollectionError(Exception):
    """
    Raised when a ChromaDB collection cannot be created, opened, or
    validated.

    Examples: collection name conflict, schema version mismatch between
    an existing collection and the current config, or an attempt to
    access a collection that does not exist.
    """
    def __init__(self, message: str):
        super().__init__(message)


class PersistenceError(Exception):
    """
    Raised when the persistence layer encounters a storage-level error.

    Examples: the persist directory is not writable, the disk is full,
    or the ChromaDB on-disk files are corrupted.
    """
    def __init__(self, message: str):
        super().__init__(message)


class StorageValidationError(Exception):
    """
    Raised when input documents fail pre-storage validation.

    Examples: duplicate document IDs within a single batch, an
    EmbeddedDocument with an empty embedding, or a metadata value
    that cannot be serialised to the ChromaDB metadata format
    (only str, int, float, bool are supported).
    """
    def __init__(self, message: str):
        super().__init__(message)


class RetrievalError(Exception):
    """
    Raised when the retrieval pipeline encounters an unrecoverable error
    that does not fit a more specific category — for example, when the
    ChromaDB collection does not exist at query time.
    """
    def __init__(self, message: str):
        super().__init__(message)


class QueryValidationError(Exception):
    """
    Raised when the user-supplied query string fails validation.

    Examples: empty query, query containing only whitespace, query that
    is longer than the model's maximum sequence length.
    """
    def __init__(self, message: str):
        super().__init__(message)


class QueryEmbeddingError(Exception):
    """
    Raised when the query text cannot be converted into an embedding vector.

    Wraps ``EmbeddingGenerationError`` or ``EmbeddingModelError`` in a
    retrieval-specific exception so callers of the retrieval pipeline
    do not need to import from the vectorization layer.
    """
    def __init__(self, message: str):
        super().__init__(message)


class SimilaritySearchError(Exception):
    """
    Raised when the ChromaDB similarity search fails at the database level.

    Examples: collection not found, index corruption, ChromaDB internal
    error during ``collection.query()``.
    """
    def __init__(self, message: str):
        super().__init__(message)


class MetadataFilterError(Exception):
    """
    Raised when a user-supplied metadata filter dict is invalid.

    Examples: unsupported field name, wrong value type for a known field,
    malformed filter structure.
    """
    def __init__(self, message: str):
        super().__init__(message)


# ---------------------------------------------------------------------------
# Phase 6 — Grounded Answer Generation exceptions
# ---------------------------------------------------------------------------

class LLMProviderError(Exception):
    """
    Raised when an LLM provider cannot be initialised, reaches its
    endpoint, or returns an unrecoverable error response.

    Covers: missing API key, unreachable Ollama server, HTTP 5xx from
    OpenAI, model not found, and any other provider-level failure.
    """
    def __init__(self, message: str):
        super().__init__(message)


class PromptBuildError(Exception):
    """
    Raised when the prompt builder fails to assemble a valid prompt.

    Examples: context string too long after truncation, missing required
    sections, or invalid template parameters.
    """
    def __init__(self, message: str):
        super().__init__(message)


class ContextBuildError(Exception):
    """
    Raised when the context builder cannot produce a usable context string
    from the supplied retrieved documents.

    Examples: all documents are empty, token budget is too small to fit
    even one document, or an unsupported metadata structure is encountered.
    """
    def __init__(self, message: str):
        super().__init__(message)


class AnswerGenerationError(Exception):
    """
    Raised when the answer generator fails to obtain a completion from the
    LLM provider after all retries are exhausted.

    Examples: LLM returns an empty response, response fails content
    safety filters, timeout exceeded, unexpected response schema.
    """
    def __init__(self, message: str):
        super().__init__(message)


class CitationError(Exception):
    """
    Raised when the citation builder encounters an unrecoverable error
    constructing citations from retrieved documents.

    This is always a programming error — the citation builder should
    degrade gracefully on bad metadata rather than raise for every field.
    It raises only when the input type contract is violated.
    """
    def __init__(self, message: str):
        super().__init__(message)


# ---------------------------------------------------------------------------
# Telegram metadata / retrieval isolation exceptions (Task 19, Req 18)
# ---------------------------------------------------------------------------

class UnauthorizedOwnerScope(Exception):
    """
    Raised when a client-supplied owner_id differs from the authenticated
    owner, or when an operation is attempted on data the caller does not own.
    HTTP surface: 403.
    """
    def __init__(self, message: str):
        super().__init__(message)


class ConversationNotFound(Exception):
    """
    Raised when a requested conversation_id does not exist in the system.
    HTTP surface: 404.
    """
    def __init__(self, message: str):
        super().__init__(message)


class ConversationNotOwned(Exception):
    """
    Raised when a requested conversation_id exists but does not belong
    to the authenticated owner.
    HTTP surface: 403.
    """
    def __init__(self, message: str):
        super().__init__(message)


class InvalidSenderFilter(Exception):
    """
    Raised when a sender_id filter is invalid for the selected conversation
    (e.g. sender is not a participant in that conversation).
    HTTP surface: 400.
    """
    def __init__(self, message: str):
        super().__init__(message)


class UnsupportedFilterCombination(Exception):
    """
    Raised when a combination of filter fields is mutually exclusive or
    otherwise not supported (e.g. both conversation_id and conversation_ids
    supplied simultaneously).
    HTTP surface: 400.
    """
    def __init__(self, message: str):
        super().__init__(message)


class InvalidTimestampFilter(Exception):
    """
    Raised when a timestamp_from or timestamp_to filter value cannot be
    parsed as a valid ISO-8601 datetime.
    HTTP surface: 400.
    """
    def __init__(self, message: str):
        super().__init__(message)


class VectorFilterBuildError(Exception):
    """
    Raised when the ChromaWhereBuilder fails to construct a valid
    ChromaDB where-clause from the validated filter.  Internal error —
    detail is logged only, never returned to the client.
    HTTP surface: 500 with generic message.
    """
    def __init__(self, message: str):
        super().__init__(message)


class MissingMandatoryMetadataError(Exception):
    """
    Raised during ingestion when a KnowledgeObject is missing mandatory
    metadata fields (owner_id, source) required before vector storage.
    HTTP surface: 500 (ingestion-side), detail logged with IDs only.
    """
    def __init__(self, message: str):
        super().__init__(message)
