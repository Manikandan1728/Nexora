"""
api/error_handlers.py — Centralised exception-to-HTTP-response mapping.

All exception handlers are registered here and attached to the app in
``main.py``.  Route functions raise domain exceptions from
``api/exceptions.py``; handlers here convert them to ``ErrorResponse``
bodies with the correct HTTP status code.

Security invariant: no handler ever leaks stack traces, absolute
filesystem paths, API keys, or personal data to the client.  Full details
go to the server-side logger only.
"""

from __future__ import annotations

import logging
import traceback

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.exceptions import (
    CollectionDeleteError,
    CollectionNotFoundError,
    FileTooLargeError,
    InvalidInputError,
    LLMUnavailableError,
    NexoraAPIError,
    ProcessingError,
)
from api.schemas.response_models import ErrorResponse

logger = logging.getLogger(__name__)


def _error_json(status: int, code: str, message: str, detail: str | None = None) -> JSONResponse:
    """Build a ``JSONResponse`` from ``ErrorResponse`` fields."""
    body = ErrorResponse(error=code, message=message, detail=detail)
    return JSONResponse(status_code=status, content=body.model_dump())


# ---------------------------------------------------------------------------
# Pydantic validation errors  →  400
# ---------------------------------------------------------------------------

async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Convert Pydantic v2 ``RequestValidationError`` to a client-safe ``400``.

    Pydantic error details are safe to surface at the field level; they
    contain no secrets or internal paths.
    """
    # Flatten the errors into a single readable string — safe for the client
    messages = "; ".join(
        f"{' -> '.join(str(loc) for loc in e['loc'])}: {e['msg']}"
        for e in exc.errors()
    )
    logger.debug("Validation error on %s %s: %s", request.method, request.url.path, messages)
    return _error_json(400, "validation_error", "Request validation failed.", messages)


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------

async def invalid_input_handler(
    request: Request, exc: InvalidInputError
) -> JSONResponse:
    """``InvalidInputError`` → 400 Bad Request."""
    logger.debug("InvalidInputError on %s: %s", request.url.path, exc.message)
    return _error_json(400, "invalid_input", exc.message)


async def file_too_large_handler(
    request: Request, exc: FileTooLargeError
) -> JSONResponse:
    """``FileTooLargeError`` → 413 Content Too Large."""
    logger.debug("FileTooLargeError on %s: %s", request.url.path, exc.message)
    return _error_json(413, "file_too_large", exc.message)


async def collection_not_found_handler(
    request: Request, exc: CollectionNotFoundError
) -> JSONResponse:
    """``CollectionNotFoundError`` → 404 Not Found."""
    logger.debug("CollectionNotFoundError on %s: %s", request.url.path, exc.message)
    return _error_json(404, "collection_not_found", exc.message)


async def processing_error_handler(
    request: Request, exc: ProcessingError
) -> JSONResponse:
    """``ProcessingError`` → 500 Internal Server Error (generic client message)."""
    logger.error("ProcessingError on %s: %s", request.url.path, exc.message)
    return _error_json(500, "processing_error", "An error occurred while processing the request.")


async def collection_delete_error_handler(
    request: Request, exc: CollectionDeleteError
) -> JSONResponse:
    """``CollectionDeleteError`` → 500."""
    logger.error("CollectionDeleteError on %s: %s", request.url.path, exc.message)
    return _error_json(500, "collection_delete_error", exc.message)


async def llm_unavailable_handler(
    request: Request, exc: LLMUnavailableError
) -> JSONResponse:
    """
    ``LLMUnavailableError`` is NOT a hard error — returns 503.

    The ``/query`` service catches this and returns 200 with retrieval-only
    results, so this handler is only reached if the exception escapes the
    service layer (which should not happen in normal operation).
    """
    logger.info("LLMUnavailableError (escaped service): %s", exc.message)
    return _error_json(503, "llm_unavailable", exc.message)


async def generic_nexora_error_handler(
    request: Request, exc: NexoraAPIError
) -> JSONResponse:
    """Catch-all for any ``NexoraAPIError`` subclass not handled above."""
    logger.error("Unhandled NexoraAPIError on %s: %s", request.url.path, exc.message)
    return _error_json(exc.http_status, "api_error", "An internal error occurred.")


# ---------------------------------------------------------------------------
# Starlette HTTP exceptions (e.g. 405 Method Not Allowed)
# ---------------------------------------------------------------------------

async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Map Starlette ``HTTPException`` to ``ErrorResponse`` shape."""
    detail = str(exc.detail) if exc.detail else None
    logger.debug("HTTPException %d on %s: %s", exc.status_code, request.url.path, detail)
    return _error_json(exc.status_code, "http_error", detail or "HTTP error.", None)


# ---------------------------------------------------------------------------
# Unhandled exceptions  →  500
# ---------------------------------------------------------------------------

async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Catch-all fallback for any unhandled exception.

    Logs the full traceback server-side; returns a safe generic message to
    the client with no stack trace, paths, or secrets.
    """
    tb = traceback.format_exc()
    logger.error(
        "Unhandled exception on %s %s:\n%s",
        request.method,
        request.url.path,
        tb,
    )
    return _error_json(
        500,
        "internal_error",
        "An unexpected internal error occurred. Please try again later.",
    )


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------

def register_handlers(app) -> None:
    """
    Attach all exception handlers to the FastAPI *app* instance.

    Called once from ``api/main.py`` during app construction.

    Args:
        app: The ``FastAPI`` application instance.
    """
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(InvalidInputError, invalid_input_handler)
    app.add_exception_handler(FileTooLargeError, file_too_large_handler)
    app.add_exception_handler(CollectionNotFoundError, collection_not_found_handler)
    app.add_exception_handler(ProcessingError, processing_error_handler)
    app.add_exception_handler(CollectionDeleteError, collection_delete_error_handler)
    app.add_exception_handler(LLMUnavailableError, llm_unavailable_handler)
    app.add_exception_handler(NexoraAPIError, generic_nexora_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
