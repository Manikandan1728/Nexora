class InvalidInputError(Exception):
    """
    Raised when the input path is invalid.
    """
    def __init__(self, message: str):
        super().__init__(message)

class ZipValidationError(Exception):
    """
    Raised when ZIP validation fails.
    """
    def __init__(self, message: str):
        super().__init__(message)

class ExtractionError(Exception):
    """
    Raised when extraction of ZIP files fails.
    """
    def __init__(self, message: str):
        super().__init__(message)

class DatasetValidationError(Exception):
    """
    Raised when dataset validation fails.
    """
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
