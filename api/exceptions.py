"""
api/exceptions.py — Domain exception hierarchy for Phase 7.

All route handlers raise these exceptions; the centralised handlers in
``error_handlers.py`` convert them to HTTP responses conforming to
``ErrorResponse``.  No route function ever constructs an ``HTTPException``
directly with an ad-hoc status code.
"""

from __future__ import annotations


class NexoraAPIError(Exception):
    """Base class for all Phase 7 domain exceptions."""

    http_status: int = 500
    default_message: str = "An internal error occurred."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


class InvalidInputError(NexoraAPIError):
    """
    Raised when client-supplied input fails validation.

    Maps to HTTP 400 Bad Request.
    Examples: wrong file type, empty question, out-of-range top_k,
    malformed collection name.
    """

    http_status = 400
    default_message = "Invalid input."


class FileTooLargeError(NexoraAPIError):
    """
    Raised when an uploaded file exceeds the configured size limit.

    Maps to HTTP 413 Content Too Large.
    """

    http_status = 413
    default_message = "Uploaded file exceeds the maximum allowed size."


class CollectionNotFoundError(NexoraAPIError):
    """
    Raised when a requested ChromaDB collection does not exist.

    Maps to HTTP 404 Not Found.
    """

    http_status = 404
    default_message = "Collection not found."


class ProcessingError(NexoraAPIError):
    """
    Raised when a Phase 1-4 pipeline step fails during upload processing.

    Maps to HTTP 500 Internal Server Error.
    The client receives a generic message; full details are logged server-side.
    """

    http_status = 500
    default_message = "An error occurred while processing the uploaded file."


class LLMUnavailableError(NexoraAPIError):
    """
    Raised when the LLM provider is unavailable or times out.

    This is NOT treated as a hard HTTP 500.  The query service catches it
    and falls back to retrieval-only results with a descriptive message.
    """

    http_status = 200  # handled specially — not a hard error
    default_message = "LLM provider is unavailable; returning retrieval-only results."


class CollectionDeleteError(NexoraAPIError):
    """
    Raised when collection deletion fails partially or completely.

    Maps to HTTP 500, with partial-success detail in the response body.
    """

    http_status = 500
    default_message = "Failed to delete the collection."


# ---------------------------------------------------------------------------
# Telegram / Metadata-retrieval exceptions (Requirements 18)
# ---------------------------------------------------------------------------

class UnauthorizedOwnerScopeError(NexoraAPIError):
    """
    Client-supplied owner scope does not match authenticated owner.
    Maps to HTTP 403. No internal detail returned.
    """
    http_status = 403
    default_message = "Unauthorized owner scope."


class ConversationNotFoundError(NexoraAPIError):
    """Requested conversation does not exist. Maps to HTTP 404."""
    http_status = 404
    default_message = "Conversation not found."


class ConversationNotOwnedError(NexoraAPIError):
    """Requested conversation is not owned by the authenticated user. Maps to HTTP 403."""
    http_status = 403
    default_message = "Conversation is not owned by the authenticated user."


class InvalidSenderFilterError(NexoraAPIError):
    """sender_id is invalid for the selected conversation. Maps to HTTP 400."""
    http_status = 400
    default_message = "Invalid sender filter for the selected conversation."


class UnsupportedFilterCombinationError(NexoraAPIError):
    """Filter combination is logically contradictory or unsupported. Maps to HTTP 400."""
    http_status = 400
    default_message = "Unsupported filter combination."


class InvalidTimestampFilterError(NexoraAPIError):
    """Timestamp filter value is malformed. Maps to HTTP 400."""
    http_status = 400
    default_message = "Invalid timestamp filter value."


class VectorFilterBuildError(NexoraAPIError):
    """ChromaDB where-clause construction failed. Maps to HTTP 500 (generic to client)."""
    http_status = 500
    default_message = "An error occurred while building the search filter."


class MissingMandatoryMetadataError(NexoraAPIError):
    """Required metadata field missing at ingestion time. Maps to HTTP 500."""
    http_status = 500
    default_message = "Missing mandatory metadata during ingestion."
