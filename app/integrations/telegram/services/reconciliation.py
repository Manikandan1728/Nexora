"""
app/integrations/telegram/services/reconciliation.py
[ADDITIVE] TelegramSynchronizationReconciler — detects and repairs partial failures.
"""
from __future__ import annotations
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
_STUCK_THRESHOLD_MINUTES = 15


@dataclass
class ReconciliationReport:
    stuck_operations_found: int = 0
    cleanup_pending_messages: int = 0
    vectors_deleted_in_cleanup: int = 0
    errors: list[str] = field(default_factory=list)
    repaired: int = 0


class TelegramSynchronizationReconciler:
    """
    Detects and repairs incomplete Telegram sync operations.

    Scenarios handled:
    1. Processing states stuck in 'processing' beyond threshold → mark failed.
    2. Messages marked is_deleted=True but active chunk mappings remain → delete vectors.
    3. Messages with processing_status='cleanup_pending' → retry vector deletion.
    """

    def __init__(
        self, session: Session, vector_mutation,
        chunk_repo, processing_state_repo, message_repo,
        stuck_threshold_minutes: int = _STUCK_THRESHOLD_MINUTES,
    ) -> None:
        self._session = session
        self._vm = vector_mutation
        self._chunk_repo = chunk_repo
        self._ps_repo = processing_state_repo
        self._msg_repo = message_repo
        self._threshold = stuck_threshold_minutes

    def run(self) -> ReconciliationReport:
        report = ReconciliationReport()
        cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=self._threshold)

        # 1. Stuck processing states
        stuck = self._ps_repo.list_stuck(self._session, cutoff)
        report.stuck_operations_found = len(stuck)
        for ps in stuck:
            try:
                self._ps_repo.mark_failed(self._session, ps, "reconciliation_timeout")
                report.repaired += 1
            except Exception as exc:
                report.errors.append(f"stuck_op {ps.id}: {exc}")

        # 2. Deleted messages with lingering active chunks
        from app.integrations.telegram.db.orm_models import TelegramMessageORM, TelegramMessageChunkORM
        deleted_with_chunks = (
            self._session.query(TelegramMessageORM)
            .join(TelegramMessageChunkORM,
                  TelegramMessageORM.id == TelegramMessageChunkORM.telegram_message_record_id)
            .filter(TelegramMessageORM.is_deleted == True,
                    TelegramMessageChunkORM.is_active == True)
            .distinct()
            .all()
        )
        report.cleanup_pending_messages = len(deleted_with_chunks)
        for msg in deleted_with_chunks:
            try:
                stale_ids = self._chunk_repo.deactivate_chunks(self._session, msg.id)
                if stale_ids:
                    n = self._vm.delete_by_vector_ids(stale_ids)
                    report.vectors_deleted_in_cleanup += n
                msg.processing_status = "completed"
                self._session.flush()
                report.repaired += 1
            except Exception as exc:
                report.errors.append(f"cleanup_msg {msg.id}: {exc}")

        # 3. [ADDITIVE] Edit-specific: non-deleted messages marked cleanup_pending
        #    These have active (new) chunks but old stale vectors not yet deleted.
        cleanup_pending_msgs = (
            self._session.query(TelegramMessageORM)
            .filter(
                TelegramMessageORM.is_deleted == False,
                TelegramMessageORM.is_edited == True,
                TelegramMessageORM.processing_status == "cleanup_pending",
            )
            .all()
        )
        for msg in cleanup_pending_msgs:
            try:
                # For cleanup_pending edits, the inactive chunks contain the stale IDs
                inactive = (
                    self._session.query(TelegramMessageChunkORM)
                    .filter_by(telegram_message_record_id=msg.id, is_active=False)
                    .all()
                )
                stale_ids = [c.vector_id for c in inactive]
                if stale_ids:
                    n = self._vm.delete_by_vector_ids(stale_ids)
                    report.vectors_deleted_in_cleanup += n
                    # Hard-delete the inactive chunk mappings after successful vector deletion
                    self._chunk_repo.delete_by_vector_ids(self._session, stale_ids)
                msg.processing_status = "completed"
                msg.last_error_code = None
                self._session.flush()
                report.repaired += 1
            except Exception as exc:
                report.errors.append(f"edit_cleanup_msg {msg.id}: {exc}")

        # 4. [ADDITIVE] Edit-specific: messages where no active chunks exist but
        #    is_edited=True and processing_status is stuck (e.g., partial vector write).
        #    Detect by: is_edited=True, NOT is_deleted, processing_status in ("processing", "failed"),
        #    AND no active chunks (vectors may be partially written).
        stuck_edit_msgs = (
            self._session.query(TelegramMessageORM)
            .filter(
                TelegramMessageORM.is_deleted == False,
                TelegramMessageORM.is_edited == True,
                TelegramMessageORM.processing_status.in_(["processing", "failed"]),
            )
            .all()
        )
        for msg in stuck_edit_msgs:
            try:
                active_count = (
                    self._session.query(TelegramMessageChunkORM)
                    .filter_by(telegram_message_record_id=msg.id, is_active=True)
                    .count()
                )
                if active_count == 0:
                    # No active chunks — mark as reconciliation_required
                    msg.processing_status = "failed"
                    msg.last_error_code = "reconciliation_no_active_chunks"
                    self._session.flush()
                    report.errors.append(
                        f"stuck_edit_no_chunks msg_id={msg.telegram_message_id}"
                    )
            except Exception as exc:
                report.errors.append(f"stuck_edit_msg {msg.id}: {exc}")

        try:
            self._session.commit()
        except Exception as exc:
            report.errors.append(f"commit: {exc}")

        logger.info(
            "Reconciliation: stuck=%d cleanup=%d vectors_deleted=%d repaired=%d errors=%d",
            report.stuck_operations_found, report.cleanup_pending_messages,
            report.vectors_deleted_in_cleanup, report.repaired, len(report.errors),
        )
        return report
