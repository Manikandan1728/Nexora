"""
app/storage/vector_store/chroma_store.py — ChromaDB implementation of IVectorStore.

WHY CHROMADB
------------
ChromaDB is the best-fit vector database for this phase because:

  • Zero infrastructure — runs embedded in the Python process, writes to a
    local directory.  No Docker, no server process, no port management.
  • HNSW index — approximate nearest-neighbour search is built in and tuned
    automatically.  Phase 5 retrieval requires no additional index setup.
  • Persistent by default — ``PersistentClient`` writes an SQLite database
    and HNSW index to disk, so data survives process restarts.
  • First-class Python API — no query language, no ORM, just Python dicts
    and lists.

METADATA FLATTENING
--------------------
ChromaDB metadata values must be scalar: ``str``, ``int``, ``float``, or
``bool``.  The ``EmbeddedDocument.metadata`` dict from Phase 3 may contain
lists (e.g. ``participants``, ``message_ids``, ``attachments``).

We flatten these to strings before storage and document the keys so Phase 5
can reconstruct them.  This is the correct architectural trade-off:
  • The vector store is an index, not an object store.
  • Reconstructing Python objects from the metadata is Phase 5's concern.
  • Storing complex nested objects in ChromaDB would couple the storage
    format to the Python model class in an unportable way.

REQUIRED METADATA KEYS (written to every stored document)
----------------------------------------------------------
All of the following are extracted from ``EmbeddedDocument`` fields and
``EmbeddedDocument.metadata``.  Keys prefixed with ``_nexora_`` are
added by the store itself (not from Phase 3 metadata) to support
schema validation and housekeeping.

  document_id           str   — primary key (mirrors Chroma id)
  source_chat           str   — originating chat label
  chunk_index           int   — zero-based chunk position
  token_count           int   — token count of the text
  message_count         int   — messages in this chunk
  attachment_count      int   — attachment references
  contains_images       bool  — image attachment flag
  contains_audio        bool  — audio attachment flag
  contains_video        bool  — video attachment flag
  contains_documents    bool  — document attachment flag
  embedding_model       str   — model that produced the vector
  schema_version        str   — storage schema version
  created_at            str   — ISO-8601 creation timestamp
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from chromadb import Collection

from models.embedded_document import EmbeddedDocument
from config.vector_config import VectorStoreConfig
from app.storage.vector_store.interfaces import IVectorStore
from app.storage.vector_store.persistence import StoragePersistence
from app.storage.vector_store.collection_manager import CollectionManager
from exceptions.exceptions import (
    VectorStoreError,
    StorageValidationError,
    CollectionError,
)

logger = logging.getLogger(__name__)

# ChromaDB scalar types — the only types allowed in metadata values.
_CHROMA_SCALAR_TYPES = (str, int, float, bool)


class ChromaVectorStore(IVectorStore):
    """
    ChromaDB-backed implementation of ``IVectorStore``.

    Stores ``EmbeddedDocument`` objects as ChromaDB records with:
      • ``ids``        → ``document_id``
      • ``embeddings`` → list[float] from ``embedding`` tuple
      • ``documents``  → ``text``
      • ``metadatas``  → flattened scalar metadata dict

    Parameters
    ----------
    config : VectorStoreConfig
        Storage configuration.  All tunables are read from this object.

    Usage
    -----
    ::

        config = VectorStoreConfig(persist_directory="/tmp/nexora_test")
        store  = ChromaVectorStore(config)
        store.initialize()
        store.add_documents(embedded_docs)
        print(store.count())
        store.close()
    """

    def __init__(self, config: VectorStoreConfig) -> None:
        self._config = config
        self._persistence = StoragePersistence(config)
        self._manager: Optional[CollectionManager] = None
        self._collection: Optional[Collection] = None
        self._initialised: bool = False

    # ------------------------------------------------------------------
    # IVectorStore implementation
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """
        Prepare the store for use.

        1. Creates persist directory.
        2. Opens ChromaDB PersistentClient.
        3. Creates/opens the named collection.
        4. Validates collection schema.
        """
        if self._initialised:
            logger.debug("ChromaVectorStore already initialised — skipping.")
            return

        client = self._persistence.initialize()
        self._manager = CollectionManager(client=client, config=self._config)
        self._collection = self._manager.get_or_create()
        self._initialised = True

        logger.info(
            "ChromaVectorStore initialised.  Collection: '%s'  "
            "Documents: %d",
            self._config.collection_name,
            self._collection.count(),
        )

    def add_documents(self, documents: List[EmbeddedDocument]) -> int:
        """
        Insert ``EmbeddedDocument`` objects into ChromaDB in batches.

        Documents whose IDs already exist in the collection are skipped
        (not silently overwritten).

        Args:
            documents: List of ``EmbeddedDocument`` objects to store.

        Returns:
            Number of documents actually inserted.

        Raises:
            StorageValidationError: If ``documents`` is empty or contains
                                    invalid entries.
            VectorStoreError:       If ChromaDB raises during insertion.
        """
        self._assert_initialised()

        if not documents:
            raise StorageValidationError(
                "add_documents received an empty list.  "
                "Pass at least one EmbeddedDocument."
            )

        self._validate_documents(documents)

        # Fetch existing IDs to skip duplicates
        existing_ids = self._get_existing_ids()

        new_docs = [
            d for d in documents if d.document_id not in existing_ids
        ]
        skipped = len(documents) - len(new_docs)
        if skipped:
            logger.info(
                "add_documents: skipping %d duplicate document(s).", skipped
            )

        if not new_docs:
            logger.info("add_documents: all documents already stored; nothing to insert.")
            return 0

        inserted = 0
        batch_size = self._config.batch_size
        total_batches = (len(new_docs) + batch_size - 1) // batch_size

        for batch_num in range(total_batches):
            start = batch_num * batch_size
            end = min(start + batch_size, len(new_docs))
            batch = new_docs[start:end]

            ids = [d.document_id for d in batch]
            embeddings = [list(d.embedding) for d in batch]
            doc_texts = [d.text for d in batch]
            metadatas = [self._build_metadata(d) for d in batch]

            logger.debug(
                "add_documents: inserting batch %d/%d (%d docs).",
                batch_num + 1,
                total_batches,
                len(batch),
            )

            try:
                self._collection.add(
                    ids=ids,
                    embeddings=embeddings,
                    documents=doc_texts,
                    metadatas=metadatas,
                )
                inserted += len(batch)
            except Exception as exc:
                raise VectorStoreError(
                    f"ChromaDB insert failed on batch {batch_num + 1}: {exc}"
                ) from exc

        logger.info(
            "add_documents: inserted %d documents into '%s'.",
            inserted,
            self._config.collection_name,
        )
        return inserted

    def delete_document(self, document_id: str) -> bool:
        """
        Remove a document by ID.

        Returns:
            ``True`` if deleted, ``False`` if not found.
        """
        self._assert_initialised()

        if not document_id or not document_id.strip():
            raise StorageValidationError("document_id must be a non-empty string.")

        try:
            result = self._collection.get(ids=[document_id])
            if not result["ids"]:
                return False
            self._collection.delete(ids=[document_id])
            logger.debug("Deleted document id='%s'.", document_id)
            return True
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to delete document '{document_id}': {exc}"
            ) from exc

    def update_document(self, document: EmbeddedDocument) -> None:
        """
        Replace an existing document's text, embedding, and metadata.

        Raises:
            StorageValidationError: If the document does not exist.
            VectorStoreError:       If ChromaDB raises.
        """
        self._assert_initialised()

        # Verify it exists first
        try:
            result = self._collection.get(ids=[document.document_id])
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to check existence of '{document.document_id}': {exc}"
            ) from exc

        if not result["ids"]:
            raise StorageValidationError(
                f"Cannot update document '{document.document_id}' — "
                f"it does not exist in collection "
                f"'{self._config.collection_name}'.  "
                f"Use add_documents() to insert new documents."
            )

        try:
            self._collection.update(
                ids=[document.document_id],
                embeddings=[list(document.embedding)],
                documents=[document.text],
                metadatas=[self._build_metadata(document)],
            )
            logger.debug("Updated document id='%s'.", document.document_id)
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to update document '{document.document_id}': {exc}"
            ) from exc

    def get_document(self, document_id: str) -> Optional[Dict]:
        """
        Retrieve a document by ID.

        Returns:
            Dict with keys ``id``, ``text``, ``embedding``, ``metadata``,
            or ``None`` if not found.
        """
        self._assert_initialised()

        try:
            result = self._collection.get(
                ids=[document_id],
                include=["documents", "metadatas", "embeddings"],
            )
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to retrieve document '{document_id}': {exc}"
            ) from exc

        if not result["ids"]:
            return None

        raw_embeddings = result.get("embeddings")
        embedding_value = raw_embeddings[0].tolist() if raw_embeddings is not None else None

        return {
            "id": result["ids"][0],
            "text": result["documents"][0] if result.get("documents") else None,
            "embedding": embedding_value,
            "metadata": result["metadatas"][0] if result.get("metadatas") else {},
        }

    def count(self) -> int:
        """Return total number of stored documents."""
        self._assert_initialised()
        try:
            return self._collection.count()
        except Exception as exc:
            raise VectorStoreError(f"Failed to get document count: {exc}") from exc

    def reset(self) -> None:
        """Delete and recreate the collection.  All data is lost."""
        self._assert_initialised()
        self._collection = self._manager.reset()
        logger.warning(
            "Collection '%s' has been reset.", self._config.collection_name
        )

    def close(self) -> None:
        """Release all resources.  Idempotent."""
        if self._persistence:
            self._persistence.close()
        self._collection = None
        self._manager = None
        self._initialised = False
        logger.debug("ChromaVectorStore closed.")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _assert_initialised(self) -> None:
        """Raise if ``initialize()`` has not been called."""
        if not self._initialised or self._collection is None:
            raise VectorStoreError(
                "ChromaVectorStore is not initialised.  Call initialize() first."
            )

    def _get_existing_ids(self) -> set:
        """Return the set of all IDs currently stored in the collection."""
        try:
            result = self._collection.get(include=[])
            return set(result.get("ids", []))
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to retrieve existing IDs: {exc}"
            ) from exc

    def _build_metadata(self, doc: EmbeddedDocument) -> Dict:
        """
        Build the ChromaDB metadata dict for one ``EmbeddedDocument``.

        All values are coerced to ChromaDB-compatible scalar types.
        List values (participants, attachments, message_ids) are
        JSON-serialised to strings so they survive the round-trip.

        The metadata includes:
          - Core document identity fields
          - All Phase 2 enrichment statistics
          - Embedding model and schema version for validation
        """
        import json

        src = doc.metadata  # already-enriched dict from Phase 3

        def _scalar(value, default):
            """Return value if it is a ChromaDB scalar, else default."""
            if isinstance(value, _CHROMA_SCALAR_TYPES):
                return value
            return default

        def _list_to_str(value) -> str:
            """Serialise a list to a JSON string."""
            if isinstance(value, (list, tuple)):
                return json.dumps(list(value))
            if isinstance(value, str):
                return value
            return str(value)

        metadata = {
            # Identity
            "document_id": doc.document_id,
            "source_chat": _scalar(src.get("source_chat", ""), ""),
            "chunk_index": _scalar(src.get("chunk_index", 0), 0),
            "token_count": doc.token_count,
            # Phase 2 statistics
            "message_count": _scalar(src.get("message_count", 0), 0),
            "attachment_count": _scalar(src.get("attachment_count", 0), 0),
            "contains_images": bool(src.get("contains_images", False)),
            "contains_audio": bool(src.get("contains_audio", False)),
            "contains_video": bool(src.get("contains_video", False)),
            "contains_documents": bool(src.get("contains_documents", False)),
            "conversation_duration_seconds": _scalar(
                src.get("conversation_duration_seconds", 0.0), 0.0
            ),
            "average_message_length": _scalar(
                src.get("average_message_length", 0.0), 0.0
            ),
            # Participant / attachment lists (serialised)
            "participants": _list_to_str(src.get("participants", [])),
            "attachments": _list_to_str(src.get("attachments", [])),
            "message_ids": _list_to_str(src.get("message_ids", [])),
            # Timestamps
            "start_timestamp": _scalar(src.get("start_timestamp", ""), ""),
            "end_timestamp": _scalar(src.get("end_timestamp", ""), ""),
            # Embedding provenance
            "embedding_model": doc.model_name,
            "embedding_dim": doc.embedding_dim,
            # Schema housekeeping
            "schema_version": self._config.schema_version,
            "created_at": doc.created_at,
        }

        return metadata

    @staticmethod
    def _validate_documents(documents: List[EmbeddedDocument]) -> None:
        """
        Validate a list of EmbeddedDocuments before insertion.

        Checks:
          • All items are ``EmbeddedDocument`` instances.
          • No duplicate ``document_id`` values within the batch.
          • Each embedding is non-empty.

        Raises:
            StorageValidationError: On first violation found.
        """
        seen_ids: set = set()
        for i, doc in enumerate(documents):
            if not isinstance(doc, EmbeddedDocument):
                raise StorageValidationError(
                    f"Item at index {i} is not an EmbeddedDocument "
                    f"(got {type(doc).__name__})."
                )
            if doc.document_id in seen_ids:
                raise StorageValidationError(
                    f"Duplicate document_id '{doc.document_id}' at index {i}."
                )
            seen_ids.add(doc.document_id)
            if not doc.embedding:
                raise StorageValidationError(
                    f"Document '{doc.document_id}' has an empty embedding."
                )
