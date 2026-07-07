"""
api/services/collection_service.py — List and delete ChromaDB collections.

All ChromaDB I/O is synchronous (no async driver).  The route layer runs
these calls via ``run_in_threadpool`` so they don't block the event loop.
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import List

import chromadb

from api.config import APISettings
from api.exceptions import CollectionDeleteError, CollectionNotFoundError, InvalidInputError
from api.schemas.response_models import CollectionInfo

logger = logging.getLogger(__name__)

# ChromaDB collection name pattern (same as in request_models.py)
_UNSAFE_PATH_RE = re.compile(r"[/\\]|\.\.")


def _validate_name(name: str) -> None:
    """Reject path-traversal or empty collection names before any FS access."""
    if not name or not name.strip():
        raise InvalidInputError("Collection name must not be empty.")
    if _UNSAFE_PATH_RE.search(name):
        raise InvalidInputError(
            "Collection name must not contain path separators or '..'."
        )


def list_collections(settings: APISettings) -> List[CollectionInfo]:
    """
    Return metadata for every ChromaDB collection in the vectors root.

    Opens a ``PersistentClient`` in read-only mode, lists collections, and
    extracts counts and metadata.  Returns an empty list if the vectors
    directory does not exist or contains no collections.

    Args:
        settings: Injected ``APISettings`` (provides ``vectors_root``).

    Returns:
        List of ``CollectionInfo`` objects, one per collection.
    """
    vectors_dir = settings.vectors_root
    if not vectors_dir.exists():
        logger.debug("Vectors directory does not exist; returning empty list.")
        return []

    # Open the client at the root persist dir
    try:
        client = chromadb.PersistentClient(path=str(vectors_dir))
        raw_collections = client.list_collections()
    except Exception as exc:
        logger.warning("Could not open ChromaDB to list collections: %s", exc)
        return []

    result: List[CollectionInfo] = []
    for col in raw_collections:
        try:
            collection = client.get_collection(col.name)
            meta = collection.metadata or {}
            result.append(
                CollectionInfo(
                    name=col.name,
                    document_count=collection.count(),
                    embedding_model=meta.get("embedding_model", "unknown"),
                    schema_version=meta.get("schema_version", "unknown"),
                )
            )
        except Exception as exc:
            logger.warning("Could not read collection %r: %s", col.name, exc)

    logger.info("Listed %d collection(s).", len(result))
    return result


def delete_collection(name: str, settings: APISettings) -> None:
    """
    Delete a ChromaDB collection and its persistence directory.

    Args:
        name: Collection name to delete.  Validated for path safety.
        settings: Injected ``APISettings``.

    Raises:
        InvalidInputError:       If the name contains path-traversal chars.
        CollectionNotFoundError: If the collection does not exist.
        CollectionDeleteError:   If deletion fails partially or completely.
    """
    _validate_name(name)

    vectors_dir = settings.vectors_root

    # Verify the collection exists in ChromaDB
    try:
        client = chromadb.PersistentClient(path=str(vectors_dir))
        existing = [c.name for c in client.list_collections()]
    except Exception as exc:
        raise CollectionDeleteError(
            f"Could not connect to vector store: {exc}"
        ) from exc

    if name not in existing:
        raise CollectionNotFoundError(f"Collection '{name}' does not exist.")

    # Delete from ChromaDB index
    try:
        client.delete_collection(name)
        logger.info("Deleted collection '%s' from ChromaDB index.", name)
    except Exception as exc:
        raise CollectionDeleteError(
            f"ChromaDB deletion failed for '{name}': {exc}"
        ) from exc

    logger.info("Collection '%s' deleted successfully.", name)
