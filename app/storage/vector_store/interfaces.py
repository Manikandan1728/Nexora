"""
app/storage/vector_store/interfaces.py — Abstract interface for vector stores.

WHY AN INTERFACE EXISTS
-----------------------
The rest of the pipeline (Phase 5 retrieval, Phase 6 RAG) must be
decoupled from the concrete storage backend.  If we hard-coded ChromaDB
calls throughout the pipeline, switching to Qdrant or FAISS would require
rewriting every caller.

The ``IVectorStore`` interface defines the *contract* that any backend
must satisfy.  ``ChromaVectorStore`` implements this contract for ChromaDB.
A future ``QdrantVectorStore`` or ``FAISSVectorStore`` would implement the
same interface without requiring any changes to the pipeline orchestrators.

This follows the Dependency Inversion Principle (SOLID): high-level modules
(Phase4Pipeline) depend on the abstraction (IVectorStore), not on the
concrete implementation (ChromaVectorStore).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from models.embedded_document import EmbeddedDocument


class IVectorStore(ABC):
    """
    Abstract base class for all vector store backends.

    Every public method represents a capability that any compliant backend
    must provide.  Implementations are free to use any underlying storage
    engine (ChromaDB, Qdrant, FAISS, Milvus, etc.) as long as they honour
    the contracts documented here.

    Storage is write-oriented in Phase 4:
      - ``initialize()``       — prepare the backend for use
      - ``add_documents()``    — bulk-insert EmbeddedDocument objects
      - ``delete_document()``  — remove one document by ID
      - ``update_document()``  — replace one document's content and vector
      - ``get_document()``     — retrieve one document by ID
      - ``count()``            — return total stored document count
      - ``reset()``            — wipe the collection (dangerous; tests only)
      - ``close()``            — release all held resources gracefully

    No retrieval, search, similarity, or RAG methods are defined here.
    Those belong to Phase 5.
    """

    @abstractmethod
    def initialize(self) -> None:
        """
        Prepare the vector store for use.

        Implementations must:
          • Create the persist directory if it does not exist.
          • Open or create the ChromaDB client.
          • Create or open the named collection.
          • Validate that an existing collection's schema matches the
            current configuration (model name, schema version).

        Must be called before any other method.

        Raises:
            VectorStoreError:    If the client cannot be created.
            CollectionError:     If the collection cannot be opened or
                                 its schema is incompatible.
            PersistenceError:    If the persist directory is not writable.
        """

    @abstractmethod
    def add_documents(self, documents: List[EmbeddedDocument]) -> int:
        """
        Insert a list of ``EmbeddedDocument`` objects into the store.

        Documents with IDs that already exist in the store are skipped
        (upsert semantics are not used; call ``update_document`` for
        explicit updates).

        Args:
            documents: Non-empty list of ``EmbeddedDocument`` objects.

        Returns:
            Number of documents actually inserted (excluding skipped
            duplicates).

        Raises:
            StorageValidationError: If the input list is invalid.
            VectorStoreError:       If the backend raises during insert.
        """

    @abstractmethod
    def delete_document(self, document_id: str) -> bool:
        """
        Remove the document with the given ID from the store.

        Args:
            document_id: The ``EmbeddedDocument.document_id`` to remove.

        Returns:
            ``True`` if the document existed and was deleted.
            ``False`` if the document was not found (not an error).

        Raises:
            VectorStoreError: If the backend raises during deletion.
        """

    @abstractmethod
    def update_document(self, document: EmbeddedDocument) -> None:
        """
        Replace an existing document with new content and/or embedding.

        The document must already exist (identified by ``document_id``).
        This is a full replace, not a partial update.

        Args:
            document: The replacement ``EmbeddedDocument``.

        Raises:
            StorageValidationError: If the document does not exist.
            VectorStoreError:       If the backend raises during update.
        """

    @abstractmethod
    def get_document(self, document_id: str) -> Optional[Dict]:
        """
        Retrieve a stored document by ID.

        Returns a plain ``dict`` rather than an ``EmbeddedDocument`` to
        avoid coupling callers to the model class.  The dict contains:
          - ``id``        : document_id
          - ``text``      : stored document text
          - ``embedding`` : list[float] or None
          - ``metadata``  : dict of stored metadata

        Args:
            document_id: The ID to look up.

        Returns:
            Dict with the document data, or ``None`` if not found.

        Raises:
            VectorStoreError: If the backend raises during retrieval.
        """

    @abstractmethod
    def count(self) -> int:
        """
        Return the total number of documents currently in the store.

        Returns:
            Non-negative integer count.

        Raises:
            VectorStoreError: If the backend raises.
        """

    @abstractmethod
    def reset(self) -> None:
        """
        Delete and recreate the collection, removing all stored data.

        **Destructive operation** — intended for testing only.

        Raises:
            VectorStoreError: If the backend raises during reset.
        """

    @abstractmethod
    def close(self) -> None:
        """
        Release all resources held by this store instance.

        After ``close()`` is called, no other methods may be called
        on this instance.  Implementations must be idempotent (calling
        ``close()`` multiple times must not raise).
        """
