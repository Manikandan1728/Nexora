"""
api/services/upload_service.py — Orchestrates Phase 1-4 for an uploaded ZIP.

Security controls applied here (not in the route):
  - Magic-byte validation (PK\\x03\\x04).
  - Filename sanitisation and UUID-based internal naming.
  - Size enforcement before buffering completes.
  - No absolute paths in any returned data structure.

All Phase 1-4 calls are synchronous/CPU-bound; the route layer wraps this
function in ``run_in_threadpool``.
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import BinaryIO, List

from api.config import APISettings
from api.exceptions import InvalidInputError, ProcessingError
from api.schemas.response_models import PhaseStatus, UploadResponse

logger = logging.getLogger(__name__)

# ZIP magic bytes: local file header signature
_ZIP_MAGIC = b"PK\x03\x04"
_READ_CHUNK = 64 * 1024  # 64 KB streaming read


def _generate_collection_name(stem: str) -> str:
    """
    Generate a filesystem-safe, collision-resistant collection name.

    Uses a UUID4 so the name is never derived from untrusted user input.
    The *stem* is used only as a human-readable prefix (already sanitised
    by the caller).

    Args:
        stem: Sanitised base name (letters/digits only).

    Returns:
        A collection name like ``"nexora_<stem8chars>_<uuid8chars>"``.
    """
    uid = uuid.uuid4().hex[:8]
    safe_stem = "".join(c if c.isalnum() else "" for c in stem.lower())[:12] or "upload"
    return f"nexora_{safe_stem}_{uid}"


def _sanitise_filename(raw: str) -> str:
    """
    Reject or strip dangerous filename components.

    Returns:
        A safe stem string (letters, digits, underscores only — no extension).

    Raises:
        InvalidInputError: If the filename contains null bytes, path
                           separators, non-printable characters, or ``..``.
    """
    if not raw:
        return "upload"

    if "\x00" in raw:
        raise InvalidInputError("Filename contains null bytes.")

    if any(c in raw for c in ("/", "\\", "..")):
        raise InvalidInputError("Filename contains path separators or '..'.")

    if not all(c.isprintable() for c in raw):
        raise InvalidInputError("Filename contains non-printable characters.")

    # Strip directory components
    stem = Path(raw).stem

    # Keep only safe characters for a label (not used in paths)
    safe = "".join(c if (c.isalnum() or c in ("_", "-")) else "_" for c in stem)
    return safe or "upload"


def run_upload_pipeline(
    file_obj: BinaryIO,
    original_filename: str,
    settings: APISettings,
) -> UploadResponse:
    """
    Execute Phase 1 → Phase 2 → Phase 3 → Phase 4 for an uploaded ZIP.

    Args:
        file_obj:          File-like object (already opened, positioned at 0).
        original_filename: Raw filename from the HTTP request.
        settings:          Injected API settings.

    Returns:
        ``UploadResponse`` with per-phase status, counts, and collection name.
        Never includes absolute filesystem paths.

    Raises:
        InvalidInputError: On filename issues or failed magic-byte check.
        FileTooLargeError: If the file exceeds ``settings.max_upload_bytes``
                           (checked during streaming save).
        ProcessingError:   If any pipeline phase raises an unexpected error.
    """
    from api.exceptions import FileTooLargeError

    wall_start = time.perf_counter()
    phase_statuses: List[PhaseStatus] = []

    # ── 1. Sanitise and validate filename ────────────────────────────
    safe_stem = _sanitise_filename(original_filename)

    # ── 2. Check magic bytes (first 4 bytes) ─────────────────────────
    header = file_obj.read(4)
    if header[:4] != _ZIP_MAGIC:
        raise InvalidInputError(
            "File is not a valid ZIP archive (magic bytes check failed)."
        )
    file_obj.seek(0)

    # ── 3. Stream to disk with size check ────────────────────────────
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    internal_name = f"{uuid.uuid4().hex}.zip"
    dest_path = settings.upload_dir / internal_name

    total_written = 0
    try:
        with open(dest_path, "wb") as out_fh:
            while True:
                chunk = file_obj.read(_READ_CHUNK)
                if not chunk:
                    break
                total_written += len(chunk)
                if total_written > settings.max_upload_bytes:
                    out_fh.close()
                    dest_path.unlink(missing_ok=True)
                    raise FileTooLargeError(
                        f"Upload exceeds {settings.max_upload_bytes} bytes."
                    )
                out_fh.write(chunk)
    except (InvalidInputError, FileTooLargeError):
        raise
    except Exception as exc:
        dest_path.unlink(missing_ok=True)
        raise ProcessingError(f"Failed to save uploaded file: {exc}") from exc

    logger.info(
        "Upload saved: internal_name=%s  bytes=%d", internal_name, total_written
    )

    # ── 4. Generate collection name ───────────────────────────────────
    collection_name = _generate_collection_name(safe_stem)
    persist_dir = str(settings.vectors_root)  # shared root — all collections live here

    # ── 5. Phase 1 — Ingestion ────────────────────────────────────────
    try:
        from pipeline.phase1_pipeline import Phase1Pipeline

        chat = Phase1Pipeline(
            input_path=str(dest_path),
            extract_root=str(settings.extract_root),
        ).run()
        messages_parsed = chat.metadata.total_messages
        phase_statuses.append(PhaseStatus(phase="phase1", status="success"))
        logger.info("Phase 1 complete.  Messages: %d", messages_parsed)
    except Exception as exc:
        dest_path.unlink(missing_ok=True)
        phase_statuses.append(
            PhaseStatus(phase="phase1", status="failed", detail="Ingestion failed.")
        )
        logger.error("Phase 1 failed: %s", exc)
        raise ProcessingError("Phase 1 (ingestion) failed.") from exc

    # ── 6. Phase 2 — Chunking ─────────────────────────────────────────
    try:
        from app.documents.phase2_pipeline import Phase2Pipeline

        documents = Phase2Pipeline(chat).run()
        chunks_created = len(documents)
        phase_statuses.append(PhaseStatus(phase="phase2", status="success"))
        logger.info("Phase 2 complete.  Chunks: %d", chunks_created)
    except Exception as exc:
        dest_path.unlink(missing_ok=True)
        phase_statuses.append(
            PhaseStatus(phase="phase2", status="failed", detail="Chunking failed.")
        )
        logger.error("Phase 2 failed: %s", exc)
        raise ProcessingError("Phase 2 (chunking) failed.") from exc

    # ── 7. Phase 3 — Embedding ────────────────────────────────────────
    try:
        from app.vectorization.embedding_pipeline import EmbeddingPipeline

        embedded = EmbeddingPipeline(documents, batch_size=32).run()
        phase_statuses.append(PhaseStatus(phase="phase3", status="success"))
        logger.info("Phase 3 complete.  Embeddings: %d", len(embedded))
    except Exception as exc:
        dest_path.unlink(missing_ok=True)
        phase_statuses.append(
            PhaseStatus(phase="phase3", status="failed", detail="Embedding failed.")
        )
        logger.error("Phase 3 failed: %s", exc)
        raise ProcessingError("Phase 3 (embedding) failed.") from exc

    # ── 8. Phase 4 — Storage ─────────────────────────────────────────
    try:
        from app.storage.vector_store.phase4_pipeline import Phase4Pipeline
        from config.vector_config import VectorStoreConfig

        store_cfg = VectorStoreConfig(
            collection_name=collection_name,
            persist_directory=persist_dir,
            distance_metric="cosine",
            batch_size=100,
            embedding_model="BAAI/bge-m3",
            schema_version="1.0.0",
        )
        summary = Phase4Pipeline(embedded, config=store_cfg).run()
        vectors_indexed = summary.final_count
        phase_statuses.append(PhaseStatus(phase="phase4", status="success"))
        logger.info("Phase 4 complete.  Vectors: %d", vectors_indexed)
    except Exception as exc:
        dest_path.unlink(missing_ok=True)
        phase_statuses.append(
            PhaseStatus(phase="phase4", status="failed", detail="Storage failed.")
        )
        logger.error("Phase 4 failed: %s", exc)
        raise ProcessingError("Phase 4 (storage) failed.") from exc

    elapsed = time.perf_counter() - wall_start

    return UploadResponse(
        collection_name=collection_name,
        messages_parsed=messages_parsed,
        chunks_created=chunks_created,
        vectors_indexed=vectors_indexed,
        phase_statuses=phase_statuses,
        elapsed_seconds=round(elapsed, 3),
    )
