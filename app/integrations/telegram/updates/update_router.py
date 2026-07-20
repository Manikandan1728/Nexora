"""
app/integrations/telegram/updates/update_router.py
[ADDITIVE] Central dispatcher for Telegram update events.

Routes:
  new_message      → TelegramIngestionPolicy (existing path)
  edited_message   → TelegramEditSynchronizationService
  deleted_message  → TelegramDeleteSynchronizationService

This router is the single entry point for both mock events (now) and
live TDLib events (future). TDLib will be a transport adapter only.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TelegramUpdateResult:
    event_type: str
    status: str
    message_id: str
    details: dict = field(default_factory=dict)


class TelegramUpdateRouter:
    """
    Routes Telegram events to the appropriate synchronization service.
    All business logic lives in the services — this class only dispatches.
    """

    def __init__(self, session_factory, vector_collection=None) -> None:
        self._session_factory = session_factory
        self._vector_collection = vector_collection

    def handle(self, event: dict[str, Any], owner_id: str) -> TelegramUpdateResult:
        """
        Route one Telegram event dict to the correct handler.
        Always returns a TelegramUpdateResult — never raises.
        """
        event_type = self._detect_event_type(event)
        msg_id = str(event.get("message_id", ""))

        try:
            if event_type == "deleted_message":
                return self._handle_delete(event, owner_id, msg_id)
            elif event_type == "edited_message":
                return self._handle_edit(event, owner_id, msg_id)
            else:
                return self._handle_new(event, owner_id, msg_id)
        except Exception as exc:
            logger.warning("UpdateRouter: unhandled error event=%r: %s", msg_id, exc)
            return TelegramUpdateResult(
                event_type=event_type, status="error",
                message_id=msg_id, details={"error": str(exc)},
            )

    @staticmethod
    def _detect_event_type(event: dict) -> str:
        if event.get("is_deleted"):
            return "deleted_message"
        if event.get("is_edited"):
            return "edited_message"
        return "new_message"

    def _handle_new(self, event: dict, owner_id: str, msg_id: str) -> TelegramUpdateResult:
        """Route new messages through the existing normalizer + policy path."""
        from app.integrations.telegram.mapping.telegram_normalizer import TelegramNormalizer
        from app.integrations.telegram.services.ingestion_policy import TelegramIngestionPolicy, IngestionAction
        from datetime import datetime, timezone

        class _AlwaysEnabled:
            def is_indexing_enabled(self, o, c): return True
            def get_indexing_enabled_at(self, o, c): return None
            def is_account_owner(self, o, a): return True

        class _NeverProcessed:
            def is_already_processed(self, a, c, m): return False

        normalizer = TelegramNormalizer()
        policy = TelegramIngestionPolicy(_AlwaysEnabled(), _NeverProcessed())
        objects = normalizer.normalize(event, owner_id=owner_id)
        statuses = []
        for obj in objects:
            decision = policy.decide(obj)
            statuses.append(decision.action.value)
        return TelegramUpdateResult(
            event_type="new_message", status="processed",
            message_id=msg_id, details={"actions": statuses},
        )

    def _handle_edit(self, event: dict, owner_id: str, msg_id: str) -> TelegramUpdateResult:
        from app.integrations.telegram.services.edit_sync import (
            TelegramEditSynchronizationService, TelegramEditEvent,
        )
        from app.integrations.telegram.repositories import (
            SqliteTelegramMessageRepository, SqliteTelegramMessageChunkRepository,
            SqliteTelegramProcessingStateRepository, SqliteTelegramTombstoneRepository,
        )
        from app.integrations.telegram.services.vector_mutation import VectorMutationService

        session = self._session_factory()
        vm = VectorMutationService(self._vector_collection) if self._vector_collection else _NoopVM()
        svc = TelegramEditSynchronizationService(
            session=session,
            vector_mutation=vm,
            message_repo=SqliteTelegramMessageRepository(),
            chunk_repo=SqliteTelegramMessageChunkRepository(),
            processing_state_repo=SqliteTelegramProcessingStateRepository(),
            tombstone_repo=SqliteTelegramTombstoneRepository(),
        )
        edit_event = TelegramEditEvent(
            owner_id=owner_id,
            source_account_id=str(event.get("account_id", "")),
            conversation_id=str(event.get("chat_id", "")),
            source_message_id=msg_id,
            new_text=event.get("text"),
            new_content_type=event.get("message_type", "text"),
        )
        result = svc.synchronize(edit_event)
        session.close()
        return TelegramUpdateResult(
            event_type="edited_message", status=result.status,
            message_id=msg_id,
            details={
                "previous_version": result.previous_version,
                "current_version": result.current_version,
                "replacement_vectors": result.replacement_vector_count,
                "deleted_vectors": result.deleted_vector_count,
                "cleanup_pending": result.cleanup_pending,
            },
        )

    def _handle_delete(self, event: dict, owner_id: str, msg_id: str) -> TelegramUpdateResult:
        from app.integrations.telegram.services.delete_sync import (
            TelegramDeleteSynchronizationService, TelegramDeleteEvent,
        )
        from app.integrations.telegram.repositories import (
            SqliteTelegramMessageRepository, SqliteTelegramMessageChunkRepository,
            SqliteTelegramProcessingStateRepository, SqliteTelegramTombstoneRepository,
        )
        from app.integrations.telegram.services.vector_mutation import VectorMutationService

        session = self._session_factory()
        vm = VectorMutationService(self._vector_collection) if self._vector_collection else _NoopVM()
        svc = TelegramDeleteSynchronizationService(
            session=session,
            vector_mutation=vm,
            message_repo=SqliteTelegramMessageRepository(),
            chunk_repo=SqliteTelegramMessageChunkRepository(),
            processing_state_repo=SqliteTelegramProcessingStateRepository(),
            tombstone_repo=SqliteTelegramTombstoneRepository(),
        )
        del_event = TelegramDeleteEvent(
            owner_id=owner_id,
            source_account_id=str(event.get("account_id", "")),
            conversation_id=str(event.get("chat_id", "")),
            source_message_id=msg_id,
        )
        result = svc.synchronize(del_event)
        session.close()
        return TelegramUpdateResult(
            event_type="deleted_message", status=result.status,
            message_id=msg_id,
            details={
                "deleted_vectors": result.deleted_vector_count,
                "deleted_files": result.deleted_file_count,
                "cleanup_pending": result.cleanup_pending,
            },
        )


class _NoopVM:
    """No-op vector mutation for tests without a real ChromaDB collection."""
    def upsert_chunks(self, chunks): return 0
    def delete_by_vector_ids(self, ids): return 0
    def delete_by_source_message(self, **kw): return 0
