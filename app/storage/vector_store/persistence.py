"""
app/storage/vector_store/persistence.py — Storage directory and health management.

WHY THIS MODULE EXISTS
----------------------
ChromaDB's PersistentClient expects its persist directory to already exist
and to be writable.  If we pass a non-existent path, it raises a confusing
internal error.  If we pass a read-only path, data is silently lost.

``StoragePersistence`` centralises all directory-level concerns:
  • Creating the persist directory (including parents) on first use.
  • Validating that the directory is writable before the client opens.
  • Performing a lightweight health check after the client is initialised.
  • Closing the ChromaDB client gracefully on shutdown.

Keeping these concerns here instead of in ``ChromaVectorStore`` means
the store class stays focused on the ChromaDB API, while all OS-level
I/O concerns are isolated in one testable place.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import chromadb

from config.vector_config import VectorStoreConfig
from exceptions.exceptions import PersistenceError, VectorStoreError

logger = logging.getLogger(__name__)


class StoragePersistence:
    """
    Manages the lifecycle of the ChromaDB ``PersistentClient``.

    Responsibilities:
      1. Validate and create the persist directory.
      2. Initialise the ``chromadb.PersistentClient``.
      3. Perform a health check (heartbeat ping).
      4. Close the client gracefully.

    Parameters
    ----------
    config : VectorStoreConfig
        Configuration object containing ``persist_directory`` and all
        other storage parameters.
    """

    def __init__(self, config: VectorStoreConfig) -> None:
        self._config = config
        self._client: Optional[chromadb.PersistentClient] = None
        self._closed: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def initialize(self) -> chromadb.PersistentClient:
        """
        Create the persist directory (if needed), open the ChromaDB
        ``PersistentClient``, and return it.

        Returns:
            An open ``chromadb.PersistentClient`` instance.

        Raises:
            PersistenceError: If the directory cannot be created or is
                              not writable.
            VectorStoreError: If the ChromaDB client cannot be opened.
        """
        if self._closed:
            raise VectorStoreError(
                "StoragePersistence has already been closed.  "
                "Create a new instance to re-initialise."
            )

        self._ensure_directory()

        logger.info(
            "Opening ChromaDB PersistentClient at '%s'.",
            self._config.persist_directory,
        )
        try:
            self._client = chromadb.PersistentClient(
                path=self._config.persist_directory
            )
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to open ChromaDB client at "
                f"'{self._config.persist_directory}': {exc}"
            ) from exc

        self._health_check()
        return self._client

    @property
    def client(self) -> Optional[chromadb.PersistentClient]:
        """The open ChromaDB client, or ``None`` before ``initialize()``."""
        return self._client

    def close(self) -> None:
        """
        Release the ChromaDB client.

        Idempotent — safe to call multiple times.
        """
        if self._closed:
            return
        if self._client is not None:
            logger.debug("Closing ChromaDB client.")
            # chromadb.PersistentClient does not expose an explicit close()
            # method in v1.x; setting to None releases the reference so the
            # garbage collector can clean up file handles.
            self._client = None
        self._closed = True
        logger.debug("StoragePersistence closed.")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_directory(self) -> None:
        """
        Create the persist directory and all parent directories if they
        do not already exist, then verify the directory is writable.

        Raises:
            PersistenceError: If creation fails or the path is read-only.
        """
        path = self._config.persist_path
        logger.debug("Ensuring persist directory exists: '%s'", path)

        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PersistenceError(
                f"Cannot create persist directory '{path}': {exc}"
            ) from exc

        if not os.access(str(path), os.W_OK):
            raise PersistenceError(
                f"Persist directory '{path}' exists but is not writable."
            )

        logger.debug("Persist directory verified: '%s'", path)

    def _health_check(self) -> None:
        """
        Perform a lightweight health check on the open client.

        Calls ``client.heartbeat()`` which returns a nanosecond timestamp
        if the client is alive.  Raises ``VectorStoreError`` on failure.
        """
        if self._client is None:
            raise VectorStoreError("Cannot health-check: client is not initialised.")
        try:
            self._client.heartbeat()
            logger.debug("ChromaDB client health check passed.")
        except Exception as exc:
            raise VectorStoreError(
                f"ChromaDB client health check failed: {exc}"
            ) from exc
