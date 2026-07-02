"""
app/storage/vector_store/collection_manager.py — ChromaDB collection lifecycle.

WHY THIS MODULE EXISTS
----------------------
ChromaDB collections carry metadata that must match the configuration used
when the embeddings were produced.  Storing BGE-M3 embeddings in a
collection that was created for a different model, or with a different
schema version, produces silent data corruption during retrieval.

``CollectionManager`` is the single place that:
  • Creates a new collection with the correct HNSW metadata parameters.
  • Opens an existing collection and validates its schema against config.
  • Provides statistics (count, collection name, metadata) for logging.
  • Handles collection reset (delete + recreate).

By isolating collection lifecycle here, ``ChromaVectorStore`` only needs
to call ``manager.get_or_create()`` and then work with the returned
``chromadb.Collection`` object — it never touches
``client.create_collection`` directly.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

import chromadb
from chromadb import Collection

from config.vector_config import VectorStoreConfig
from exceptions.exceptions import CollectionError, VectorStoreError

logger = logging.getLogger(__name__)

# Keys stored in ChromaDB collection metadata for schema validation.
# These are written once at collection creation and checked on every open.
_META_EMBEDDING_MODEL = "embedding_model"
_META_SCHEMA_VERSION = "schema_version"
_META_DISTANCE_METRIC = "distance_metric"


class CollectionManager:
    """
    Manages the lifecycle of a single ChromaDB collection.

    Parameters
    ----------
    client : chromadb.PersistentClient
        An open, initialised ChromaDB client.
    config : VectorStoreConfig
        Configuration specifying collection name, distance metric, model,
        and schema version.
    """

    def __init__(
        self,
        client: chromadb.PersistentClient,
        config: VectorStoreConfig,
    ) -> None:
        self._client = client
        self._config = config
        self._collection: Optional[Collection] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_or_create(self) -> Collection:
        """
        Open an existing collection or create a new one.

        On creation:
          • Sets the HNSW distance metric via ``metadata``.
          • Records ``embedding_model``, ``schema_version``, and
            ``distance_metric`` in the collection metadata for future
            validation.

        On open:
          • Validates that the existing collection's ``embedding_model``
            and ``schema_version`` match the current configuration.
          • Logs a warning (not an error) if the distance metric differs,
            because changing the metric on an existing index is not
            supported by ChromaDB.

        Returns:
            The open ``chromadb.Collection``.

        Raises:
            CollectionError:  If schema validation fails.
            VectorStoreError: If ChromaDB raises an unexpected error.
        """
        collection_meta = {
            "hnsw:space": self._config.distance_metric,
            _META_EMBEDDING_MODEL: self._config.embedding_model,
            _META_SCHEMA_VERSION: self._config.schema_version,
            _META_DISTANCE_METRIC: self._config.distance_metric,
        }

        logger.info(
            "Opening/creating ChromaDB collection '%s' "
            "(metric=%s, model=%s, schema=%s).",
            self._config.collection_name,
            self._config.distance_metric,
            self._config.embedding_model,
            self._config.schema_version,
        )

        try:
            # get_or_create_collection: opens if exists, creates if not.
            # Passing metadata on open does not overwrite existing metadata —
            # ChromaDB ignores the metadata argument when the collection exists.
            self._collection = self._client.get_or_create_collection(
                name=self._config.collection_name,
                metadata=collection_meta,
            )
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to get or create collection "
                f"'{self._config.collection_name}': {exc}"
            ) from exc

        self._validate_collection_schema()
        return self._collection

    def reset(self) -> Collection:
        """
        Delete the existing collection (if present) and create a fresh one.

        **Destructive** — all stored documents are permanently removed.
        Intended for testing and complete re-ingestion workflows.

        Returns:
            The newly created empty ``chromadb.Collection``.

        Raises:
            VectorStoreError: If ChromaDB raises during delete or create.
        """
        logger.warning(
            "Resetting collection '%s' — all data will be lost.",
            self._config.collection_name,
        )
        try:
            existing = [
                c.name for c in self._client.list_collections()
            ]
            if self._config.collection_name in existing:
                self._client.delete_collection(self._config.collection_name)
                logger.debug(
                    "Deleted collection '%s'.", self._config.collection_name
                )
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to delete collection "
                f"'{self._config.collection_name}': {exc}"
            ) from exc

        self._collection = None
        return self.get_or_create()

    @property
    def collection(self) -> Optional[Collection]:
        """The open ``chromadb.Collection``, or ``None`` before ``get_or_create()``."""
        return self._collection

    def statistics(self) -> Dict:
        """
        Return a dict of statistics for the current collection.

        Returns:
            Dict with keys ``name``, ``count``, ``metadata``.

        Raises:
            CollectionError: If no collection has been opened yet.
        """
        if self._collection is None:
            raise CollectionError(
                "No collection is open.  Call get_or_create() first."
            )
        try:
            count = self._collection.count()
            meta = self._collection.metadata or {}
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to read collection statistics: {exc}"
            ) from exc

        return {
            "name": self._config.collection_name,
            "count": count,
            "metadata": meta,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _validate_collection_schema(self) -> None:
        """
        Check that an existing collection's schema is compatible with the
        current ``VectorStoreConfig``.

        Validates:
          • ``embedding_model`` matches ``config.embedding_model``
          • ``schema_version`` matches ``config.schema_version``

        Warns (does not raise) on distance metric mismatch because
        ChromaDB does not allow changing the metric post-creation.

        Raises:
            CollectionError: If embedding_model or schema_version mismatch.
        """
        if self._collection is None:
            return

        stored_meta = self._collection.metadata or {}

        stored_model = stored_meta.get(_META_EMBEDDING_MODEL)
        stored_schema = stored_meta.get(_META_SCHEMA_VERSION)
        stored_metric = stored_meta.get(_META_DISTANCE_METRIC)

        if stored_model and stored_model != self._config.embedding_model:
            raise CollectionError(
                f"Collection '{self._config.collection_name}' was created with "
                f"embedding model '{stored_model}', but current config specifies "
                f"'{self._config.embedding_model}'.  "
                f"Reset the collection or use the correct model."
            )

        if stored_schema and stored_schema != self._config.schema_version:
            raise CollectionError(
                f"Collection '{self._config.collection_name}' has schema version "
                f"'{stored_schema}', but current config requires "
                f"'{self._config.schema_version}'.  "
                f"Run a migration or reset the collection."
            )

        if stored_metric and stored_metric != self._config.distance_metric:
            logger.warning(
                "Collection '%s' was created with distance metric '%s', "
                "but config specifies '%s'.  The existing metric is used — "
                "reset the collection to change it.",
                self._config.collection_name,
                stored_metric,
                self._config.distance_metric,
            )

        logger.debug(
            "Collection schema validation passed for '%s'.",
            self._config.collection_name,
        )
