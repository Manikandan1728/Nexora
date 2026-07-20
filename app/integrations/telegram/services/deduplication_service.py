"""
app/integrations/telegram/services/deduplication_service.py

[ADDITIVE] — New file. No existing code is modified.

Implements idempotency for Telegram message ingestion.

The same Telegram update may arrive multiple times after reconnection or
restart. This service ensures a given message is never stored or embedded
more than once (unless it is an edit, which intentionally replaces it).

STABLE VECTOR ID SCHEME
------------------------
Every vector document ID follows the pattern:
  telegram:{account_id}:{chat_id}:{message_id}:{content_part}:{chunk_index}

Examples:
  telegram:tg_account_001:tg_chat_anu_001:tg_message_1001:text:0
  telegram:tg_account_001:tg_chat_anu_001:tg_message_1001:pdf:0
  telegram:tg_account_001:tg_chat_anu_001:tg_message_1001:pdf:1

This ID is derived deterministically from the KnowledgeObject — the same
message always produces the same vector IDs, so re-ingestion naturally
overwrites the same ChromaDB slots rather than creating duplicates.

NON-TELEGRAM SOURCE VECTOR IDs
--------------------------------
Non-Telegram sources use UUID-based IDs (from Phase 4 legacy path).
This service does not touch those IDs — the stable ID scheme is
Telegram-only. A regression test in test_phase_telegram.py confirms that
pre-existing non-Telegram vector IDs are unaffected.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from models.knowledge_object import KnowledgeObject

logger = logging.getLogger(__name__)


@runtime_checkable
class IProcessedMessageStore(Protocol):
    """Minimal interface for checking/recording processed message IDs."""
    def has_been_processed(self, vector_document_id: str) -> bool: ...
    def mark_as_processed(self, vector_document_id: str) -> None: ...
    def remove(self, vector_document_id: str) -> None: ...


class InMemoryProcessedMessageStore:
    """
    In-memory implementation of IProcessedMessageStore.
    Suitable for tests and single-process scenarios.
    A persistent implementation (SQLite/Postgres) would replace this
    in production.
    """

    def __init__(self) -> None:
        self._processed: set[str] = set()

    def has_been_processed(self, vector_document_id: str) -> bool:
        return vector_document_id in self._processed

    def mark_as_processed(self, vector_document_id: str) -> None:
        self._processed.add(vector_document_id)

    def remove(self, vector_document_id: str) -> None:
        self._processed.discard(vector_document_id)

    def clear(self) -> None:
        self._processed.clear()

    def __len__(self) -> int:
        return len(self._processed)


class TelegramDeduplicationService:
    """
    Provides idempotency checks and stable vector document ID generation
    for Telegram message ingestion.

    All generated IDs follow the scheme:
      telegram:{account_id}:{chat_id}:{message_id}:{content_part}:{chunk_index}

    Usage
    -----
    ::

        store = InMemoryProcessedMessageStore()
        dedup = TelegramDeduplicationService(store)

        # Check before processing
        vid = dedup.vector_id(obj, content_part="text", chunk_index=0)
        if dedup.is_duplicate(vid):
            return  # skip

        # After successful indexing
        dedup.mark_processed(vid)
    """

    def __init__(self, store: IProcessedMessageStore) -> None:
        self._store = store

    @staticmethod
    def vector_id(
        obj: KnowledgeObject,
        content_part: str = "text",
        chunk_index: int = 0,
    ) -> str:
        """
        Generate a stable, idempotent vector document ID for a chunk.

        The ID is fully determined by the KnowledgeObject's identity fields
        and the chunk position — calling this twice with the same arguments
        always returns the same string.

        Args:
            obj:          The KnowledgeObject being indexed.
            content_part: The content section (e.g. "text", "pdf", "image").
            chunk_index:  Zero-based chunk index within the content part.

        Returns:
            A stable vector document ID string.
        """
        return obj.vector_document_id(content_part=content_part, chunk_index=chunk_index)

    def is_duplicate(self, vector_document_id: str) -> bool:
        """
        Return True if this vector document ID has already been processed.

        Args:
            vector_document_id: The stable ID from vector_id().

        Returns:
            True when a duplicate is detected.
        """
        result = self._store.has_been_processed(vector_document_id)
        if result:
            logger.debug("Deduplication: duplicate detected for %r", vector_document_id)
        return result

    def mark_processed(self, vector_document_id: str) -> None:
        """
        Record that this vector document ID has been successfully processed.

        Args:
            vector_document_id: The stable ID from vector_id().
        """
        self._store.mark_as_processed(vector_document_id)
        logger.debug("Deduplication: marked processed %r", vector_document_id)

    def remove(self, vector_document_id: str) -> None:
        """
        Remove a vector document ID from the processed set.
        Used during edit/delete handling to allow re-processing.

        Args:
            vector_document_id: The stable ID to remove.
        """
        self._store.remove(vector_document_id)
        logger.debug("Deduplication: removed %r from processed set", vector_document_id)
