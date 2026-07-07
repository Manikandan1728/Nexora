"""
api/routes/upload.py — POST /upload

Accepts a WhatsApp ZIP, validates it, and runs Phase 1-4.
Heavy processing is offloaded to a thread pool so the event loop stays free.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile
from fastapi.concurrency import run_in_threadpool

from api.config import APISettings, get_settings
from api.exceptions import FileTooLargeError, InvalidInputError
from api.schemas.response_models import UploadResponse
from api.services import upload_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["upload"])

_ALLOWED_EXTENSION = ".zip"


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=200,
    summary="Upload and process a WhatsApp ZIP export",
)
async def upload_file(
    file: UploadFile,
    settings: Annotated[APISettings, Depends(get_settings)],
) -> UploadResponse:
    """
    Accept a ``.zip`` file, validate it, and run Phase 1 → Phase 4.

    Validation:
    - Extension must be ``.zip`` (case-insensitive).
    - Magic bytes must be ``PK\\x03\\x04``.
    - File size must not exceed ``settings.max_upload_bytes``.
    - Filename is sanitised; the raw client filename is never used in paths.

    On success, returns collection name, per-phase counts, and elapsed time.
    On partial pipeline failure, raises ``ProcessingError`` (HTTP 500) with
    a generic message; full details are logged server-side.

    Args:
        file:     Multipart file upload.
        settings: Injected ``APISettings``.

    Returns:
        ``UploadResponse`` with processing summary.
    """
    # ── Extension check ───────────────────────────────────────────────
    raw_filename = file.filename or ""
    if not raw_filename.lower().endswith(_ALLOWED_EXTENSION):
        raise InvalidInputError(
            f"Only '{_ALLOWED_EXTENSION}' files are accepted. "
            f"Received: '{raw_filename}'."
        )

    # ── Delegate to service (runs in thread pool) ─────────────────────
    result: UploadResponse = await run_in_threadpool(
        upload_service.run_upload_pipeline,
        file.file,
        raw_filename,
        settings,
    )
    logger.info(
        "Upload processed: collection=%s  messages=%d  chunks=%d  vectors=%d",
        result.collection_name,
        result.messages_parsed,
        result.chunks_created,
        result.vectors_indexed,
    )
    return result
