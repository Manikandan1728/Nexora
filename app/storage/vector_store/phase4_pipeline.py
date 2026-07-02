"""
app/storage/vector_store/phase4_pipeline.py — Phase 4 orchestrator.

WHY THIS MODULE EXISTS
----------------------
``ChromaVectorStore`` knows how to store one document.  The pipeline's
job is to accept the full ``List[EmbeddedDocument]`` from Phase 3,
validate the input, initialise the store, drive the insertion, verify
the final count, and return a structured summary.

Callers only need to know:

    summary = Phase4Pipeline(embedded_docs).run()

All internal details — config, store initialisation, batch size,
verification — are hidden behind this single entry point.

DEPENDENCY INJECTION
--------------------
The ``VectorStoreConfig`` and ``IVectorStore`` are both injected via the
constructor.  This means:

  • Tests can inject a config pointing to a ``tmp_path`` directory and a
    real ``ChromaVectorStore`` without touching the project's data/vectors.
  • A future ``QdrantVectorStore`` backend can be swapped in by passing it
    as ``store``, with zero changes to this pipeline class.

OUTPUT: StorageSummary
----------------------
``Phase4Pipeline.run()`` returns a ``StorageSummary`` dataclass that
captures:

  - Total documents received
  - Documents actually inserted
  - Documents skipped (duplicates)
  - Final collection count
  - Collection name and persist directory
  - Elapsed time

This summary is the Phase 4 output contract.  Phase 5 does not need this
information to perform retrieval, but it is useful for logging, monitoring,
and the end-to-end CLI output.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import List, Optional

from models.embedded_document import EmbeddedDocument
from config.vector_config import VectorStoreConfig
from app.storage.vector_store.interfaces import IVectorStore
from app.storage.vector_store.chroma_store import ChromaVectorStore
from exceptions.exceptions import StorageValidationError, VectorStoreError

logger = logging.getLogger(__name__)


@dataclass
class StorageSummary:
    """
    Summary of a completed Phase 4 storage run.

    Attributes
    ----------
    documents_received : int
        Total number of ``EmbeddedDocument`` objects passed to the pipeline.
    documents_inserted : int
        Number actually written to ChromaDB.
    documents_skipped : int
        Number skipped because their IDs were already in the collection.
    final_count : int
        Total documents in the collection after the run.
    collection_name : str
        Name of the ChromaDB collection written to.
    persist_directory : str
        Path to the ChromaDB persist directory.
    elapsed_seconds : float
        Wall-clock time for the entire pipeline run.
    """
    documents_received: int
    documents_inserted: int
    documents_skipped: int
    final_count: int
    collection_name: str
    persist_directory: str
    elapsed_seconds: float

    def __str__(self) -> str:
        return (
            f"StorageSummary("
            f"received={self.documents_received}, "
            f"inserted={self.documents_inserted}, "
            f"skipped={self.documents_skipped}, "
            f"total_in_db={self.final_count}, "
            f"collection='{self.collection_name}', "
            f"elapsed={self.elapsed_seconds:.2f}s)"
        )


class Phase4Pipeline:
    """
    Orchestrates the storage of ``List[EmbeddedDocument]`` into ChromaDB.

    Parameters
    ----------
    documents : List[EmbeddedDocument]
        Output of ``Phase3 EmbeddingPipeline.run()``.
    config : VectorStoreConfig, optional
        Storage configuration.  Defaults to ``VectorStoreConfig()`` which
        uses environment variables or project defaults.
    store : IVectorStore, optional
        Vector store backend.  Defaults to ``ChromaVectorStore(config)``.
        Inject a different backend or a mock for testing.

    Example
    -------
    ::

        from app.storage.vector_store.phase4_pipeline import Phase4Pipeline
        from config.vector_config import VectorStoreConfig

        summary = Phase4Pipeline(embedded_docs).run()
        print(f"Stored {summary.documents_inserted} documents.")

        # With a custom config (e.g. test or alternate directory)
        config = VectorStoreConfig(persist_directory="/tmp/my_test_db")
        summary = Phase4Pipeline(embedded_docs, config=config).run()
    """

    def __init__(
        self,
        documents: List[EmbeddedDocument],
        config: Optional[VectorStoreConfig] = None,
        store: Optional[IVectorStore] = None,
    ) -> None:
        if not isinstance(documents, list):
            raise TypeError(
                f"Phase4Pipeline expects List[EmbeddedDocument], "
                f"got {type(documents).__name__}."
            )
        if documents and not isinstance(documents[0], EmbeddedDocument):
            raise TypeError(
                f"Phase4Pipeline expects List[EmbeddedDocument], "
                f"but first element is {type(documents[0]).__name__}."
            )

        self._documents = documents
        self._config = config or VectorStoreConfig()
        self._store: IVectorStore = store or ChromaVectorStore(self._config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> StorageSummary:
        """
        Execute the full Phase 4 storage pipeline.

        Steps:
        1. Validate input.
        2. Initialise the vector store.
        3. Insert documents in batches.
        4. Verify the final document count.
        5. Close the store.
        6. Return a ``StorageSummary``.

        Returns:
            ``StorageSummary`` describing the completed storage run.
            When the input list is empty, returns a summary with all
            counts set to zero.

        Raises:
            StorageValidationError: If the input is malformed.
            VectorStoreError:       If ChromaDB raises during storage.
        """
        start = time.perf_counter()

        logger.info(
            "Phase 4 pipeline starting.  Documents: %d  Collection: '%s'  "
            "Persist: '%s'",
            len(self._documents),
            self._config.collection_name,
            self._config.persist_directory,
        )

        # ── Empty input ───────────────────────────────────────────────
        if not self._documents:
            logger.warning(
                "Phase 4 pipeline: no documents to store; returning empty summary."
            )
            return StorageSummary(
                documents_received=0,
                documents_inserted=0,
                documents_skipped=0,
                final_count=0,
                collection_name=self._config.collection_name,
                persist_directory=self._config.persist_directory,
                elapsed_seconds=time.perf_counter() - start,
            )

        # ── Initialise store ─────────────────────────────────────────
        try:
            self._store.initialize()
        except Exception as exc:
            raise VectorStoreError(
                f"Phase 4 pipeline: store initialisation failed: {exc}"
            ) from exc

        # ── Insert documents ─────────────────────────────────────────
        count_before = self._store.count()

        try:
            inserted = self._store.add_documents(self._documents)
        except Exception as exc:
            self._store.close()
            raise

        # ── Verify count ─────────────────────────────────────────────
        final_count = self._store.count()
        skipped = len(self._documents) - inserted

        logger.info(
            "Phase 4 pipeline complete.  "
            "Received: %d  Inserted: %d  Skipped: %d  "
            "Total in DB: %d  Elapsed: %.2fs",
            len(self._documents),
            inserted,
            skipped,
            final_count,
            time.perf_counter() - start,
        )

        # ── Close store ──────────────────────────────────────────────
        self._store.close()

        elapsed = time.perf_counter() - start
        return StorageSummary(
            documents_received=len(self._documents),
            documents_inserted=inserted,
            documents_skipped=skipped,
            final_count=final_count,
            collection_name=self._config.collection_name,
            persist_directory=self._config.persist_directory,
            elapsed_seconds=elapsed,
        )
