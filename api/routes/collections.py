"""
api/routes/collections.py — GET /collections  and  DELETE /collections/{name}

Collection name path parameters are treated as untrusted input and
validated for path-traversal before any filesystem or ChromaDB call.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fastapi.concurrency import run_in_threadpool

from api.config import APISettings, get_settings
from api.schemas.response_models import (
    CollectionListResponse,
    DeleteCollectionResponse,
)
from api.services import collection_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["collections"])


@router.get(
    "/collections",
    response_model=CollectionListResponse,
    summary="List all indexed collections",
)
async def list_collections(
    settings: Annotated[APISettings, Depends(get_settings)],
) -> CollectionListResponse:
    """
    Return all indexed ChromaDB collections with basic metadata.

    Never crashes on an empty store — returns ``{"collections": [], "total": 0}``.

    Args:
        settings: Injected ``APISettings``.

    Returns:
        ``CollectionListResponse`` with a list of ``CollectionInfo`` objects.
    """
    items = await run_in_threadpool(
        collection_service.list_collections,
        settings,
    )
    return CollectionListResponse(collections=items, total=len(items))


@router.delete(
    "/collections/{collection_name}",
    response_model=DeleteCollectionResponse,
    summary="Delete an indexed collection",
)
async def delete_collection(
    settings: Annotated[APISettings, Depends(get_settings)],
    collection_name: str = Path(
        ...,
        description="Collection name to delete.",
        min_length=3,
        max_length=512,
    ),
) -> DeleteCollectionResponse:
    """
    Delete a ChromaDB collection by name.

    The ``collection_name`` path parameter is validated for path-traversal
    before any filesystem or ChromaDB call — it is treated as untrusted input.

    Returns:
        HTTP 200 with ``deleted=True`` on success.
        HTTP 404 if the collection does not exist.
        HTTP 500 if deletion fails partially.

    Args:
        settings:        Injected ``APISettings``.
        collection_name: Path parameter — the collection to delete.
    """
    await run_in_threadpool(
        collection_service.delete_collection,
        collection_name,
        settings,
    )
    logger.info("Collection deleted: %s", collection_name)
    return DeleteCollectionResponse(
        collection_name=collection_name,
        deleted=True,
        message=f"Collection '{collection_name}' deleted successfully.",
    )
