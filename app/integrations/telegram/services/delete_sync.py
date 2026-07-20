"""
app/integrations/telegram/services/delete_sync.py

[ADDITIVE] Telegram delete synchronization service.

Decision Record DR-5: delete_local_media_on_source_delete defaults to False.
See config/telegram_config.py for the env var NEXORA_DELETE_LOCAL_MEDIA_ON_DELETE.

Delete flow (Phase 9):
  1. Check tombstone → idempotent return if already deleted.
  2. Load TelegramMessage.
  3. If not found → create tombstone, return safe no-op.
  4. Load all active chunk mappings.
  5. Mark message deleted in DB.
  6. Deactivate all chunk mappings.
  7. Delete all vectors from ChromaDB.
  8. Mark attachments deleted.
  9. Delete local files (if configured).
  10. Create tombstone.
  11. Mark processing success.
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.integrations.telegram.db.orm_models import (
    TelegramMessageORM, TelegramProcessingStateORM, TelegramDeletionTombstoneORM,
    TelegramAttachmentORM,
)

logger = logging.getLogger(__name__)

# Config: read once at import time; tests can override directly
_DELETE_LOCAL_MEDIA = os.environ.get("NEXORA_DELETE_LOCAL_MEDIA_ON_DELETE", "false").lower() == "true"
_MEDIA_ROOT = Path(os.environ.get("NEXORA_MEDIA_ROOT", "data/media")).resolve()


@dataclass
class TelegramDeleteEvent:
    owner_id: str
    source_account_id: str
    conversation_id: str
    source_message_id: str
    update_id: str | None = None
    deleted_at: datetime | None = None


@dataclass
class DeleteSyncResult:
    status: str               # "ok" | "skipped" | "not_found" | "cleanup_pending" | "failed"
    message_id: str
    deleted_vector_count: int
    deleted_file_count: int
    cleanup_pending: bool
    reason: str = ""


class TelegramDeleteSynchronizationService:
    """
    Synchronizes a Telegram message deletion into the database and ChromaDB.
    """

    def __init__(
        self,
        session: Session,
        vector_mutation,
        message_repo,
        chunk_repo,
        processing_state_repo,
        tombstone_repo,
        delete_local_media: bool | None = None,
        media_root: Path | None = None,
    ) -> None:
        self._session = session
        self._vm = vector_mutation
        self._msg_repo = message_repo
        self._chunk_repo = chunk_repo
        self._ps_repo = processing_state_repo
        self._tomb_repo = tombstone_repo
        self._delete_media = delete_local_media if delete_local_media is not None else _DELETE_LOCAL_MEDIA
        self._media_root = (media_root or _MEDIA_ROOT).resolve()

    def synchronize(self, event: TelegramDeleteEvent) -> DeleteSyncResult:
        """
        Process a delete event end-to-end.
        Returns DeleteSyncResult — never raises.
        """
        deleted_at = event.deleted_at or datetime.now(tz=timezone.utc)

        # Tombstone idempotency: already deleted → return safe success
        if self._tomb_repo.exists(
            self._session,
            event.source_account_id, event.conversation_id, event.source_message_id,
        ):
            return DeleteSyncResult(
                status="skipped", message_id=event.source_message_id,
                deleted_vector_count=0, deleted_file_count=0,
                cleanup_pending=False, reason="already_deleted",
            )

        # Load message
        msg = self._msg_repo.get_by_source_identity(
            self._session,
            event.source_account_id, event.conversation_id, event.source_message_id,
        )
        if msg is None:
            # Unknown message delete → create tombstone, safe no-op
            self._tomb_repo.create(self._session, TelegramDeletionTombstoneORM(
                id=str(uuid.uuid4()),
                owner_id=event.owner_id,
                source_account_id=event.source_account_id,
                conversation_id=event.conversation_id,
                source_message_id=event.source_message_id,
                deleted_at=deleted_at,
                source_update_id=event.update_id,
            ))
            self._session.commit()
            return DeleteSyncResult(
                status="not_found", message_id=event.source_message_id,
                deleted_vector_count=0, deleted_file_count=0,
                cleanup_pending=False, reason="unknown_message",
            )

        # Idempotency: message already marked deleted
        if msg.is_deleted:
            return DeleteSyncResult(
                status="skipped", message_id=event.source_message_id,
                deleted_vector_count=0, deleted_file_count=0,
                cleanup_pending=False, reason="already_marked_deleted",
            )

        # Processing state
        idempotency_key = (
            f"telegram:delete:{event.source_account_id}:"
            f"{event.conversation_id}:{event.source_message_id}:"
            f"{event.update_id or deleted_at.isoformat()}"
        )
        ps = TelegramProcessingStateORM(
            id=str(uuid.uuid4()),
            telegram_message_record_id=msg.id,
            operation_type="delete",
            status="processing",
            idempotency_key=idempotency_key,
            started_at=datetime.now(tz=timezone.utc),
        )
        existing_ps = self._ps_repo.get_by_idempotency_key(self._session, idempotency_key)
        if existing_ps and existing_ps.status == "completed":
            return DeleteSyncResult(
                status="skipped", message_id=event.source_message_id,
                deleted_vector_count=0, deleted_file_count=0,
                cleanup_pending=False, reason="processing_state_completed",
            )
        if not existing_ps:
            self._session.add(ps)
            self._session.flush()

        # Deactivate all chunk mappings and collect vector IDs
        stale_vector_ids = self._chunk_repo.deactivate_chunks(self._session, msg.id)

        # Mark message deleted
        self._msg_repo.mark_deleted(self._session, msg)

        # Mark attachments deleted
        deleted_file_count = 0
        for att in msg.attachments:
            att.is_deleted = True
            if self._delete_media and att.local_path:
                deleted_file_count += self._safe_delete_file(att.local_path)
        self._session.flush()

        # Delete vectors from ChromaDB
        deleted_vector_count = 0
        cleanup_pending = False
        try:
            if stale_vector_ids:
                deleted_vector_count = self._vm.delete_by_vector_ids(stale_vector_ids)
            # Also try metadata-filter deletion to catch any orphaned vectors
            bonus = self._vm.delete_by_source_message(
                owner_id=event.owner_id,
                source="telegram",
                source_account_id=event.source_account_id,
                conversation_id=event.conversation_id,
                source_message_id=event.source_message_id,
            )
            deleted_vector_count += bonus
        except Exception as exc:
            logger.warning("DeleteSync: vector deletion failed msg=%r: %s", event.source_message_id, exc)
            cleanup_pending = True
            msg.last_error_code = f"vector_delete_failed:{str(exc)[:64]}"
            self._session.flush()

        # Create tombstone
        self._tomb_repo.create(self._session, TelegramDeletionTombstoneORM(
            id=str(uuid.uuid4()),
            owner_id=event.owner_id,
            source_account_id=event.source_account_id,
            conversation_id=event.conversation_id,
            source_message_id=event.source_message_id,
            deleted_at=deleted_at,
            source_update_id=event.update_id,
        ))

        if not existing_ps:
            ps.status = "completed" if not cleanup_pending else "cleanup_pending"
            ps.completed_at = datetime.now(tz=timezone.utc)
            self._session.flush()

        self._session.commit()

        return DeleteSyncResult(
            status="cleanup_pending" if cleanup_pending else "ok",
            message_id=event.source_message_id,
            deleted_vector_count=deleted_vector_count,
            deleted_file_count=deleted_file_count,
            cleanup_pending=cleanup_pending,
        )

    def _safe_delete_file(self, local_path: str) -> int:
        """
        Safely delete a local media file. Only deletes files inside
        the configured media root (path-traversal protection).
        Returns 1 if deleted, 0 if skipped/missing.
        """
        try:
            resolved = (self._media_root / local_path).resolve()
            # Security: ensure resolved path is inside media root
            resolved.relative_to(self._media_root)
            if resolved.exists() and resolved.is_file():
                resolved.unlink()
                logger.debug("DeleteSync: deleted local file %s", resolved.name)
                return 1
        except (ValueError, OSError) as exc:
            logger.warning("DeleteSync: safe_delete_file skipped %r: %s", local_path, exc)
        return 0
