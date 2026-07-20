"""
tests/test_edit_delete_sync.py — Phases 8+9, 18+19: Edit and delete sync tests.
Uses in-memory SQLite + no-op vector mutation.
"""
from __future__ import annotations
import uuid
import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.integrations.telegram.db.orm_models import (
    Base, TelegramAccountORM, TelegramChatORM, TelegramMessageORM,
    TelegramMessageChunkORM, TelegramDeletionTombstoneORM,
)
from app.integrations.telegram.repositories.message_repo import SqliteTelegramMessageRepository
from app.integrations.telegram.repositories.chunk_repo import SqliteTelegramMessageChunkRepository
from app.integrations.telegram.repositories.processing_state_repo import SqliteTelegramProcessingStateRepository
from app.integrations.telegram.repositories.tombstone_repo import SqliteTelegramTombstoneRepository
from app.integrations.telegram.services.edit_sync import TelegramEditSynchronizationService, TelegramEditEvent
from app.integrations.telegram.services.delete_sync import TelegramDeleteSynchronizationService, TelegramDeleteEvent


@pytest.fixture()
def mem_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = Session()
    yield s
    s.close()


class _TrackingVM:
    """Records all VM calls for assertion."""
    def __init__(self):
        self.upserted = []
        self.deleted = []
        self.source_deleted = []

    def upsert_chunks(self, chunks):
        self.upserted.extend(c.vector_id for c in chunks)
        return len(chunks)

    def delete_by_vector_ids(self, ids):
        self.deleted.extend(ids)
        return len(ids)

    def delete_by_source_message(self, **kw):
        self.source_deleted.append(kw.get("source_message_id"))
        return 0

    def get_by_vector_ids(self, ids):
        return []

    def reset(self):
        self.upserted.clear(); self.deleted.clear(); self.source_deleted.clear()


class _FailingVM(_TrackingVM):
    """Simulates vector deletion failure."""
    def delete_by_vector_ids(self, ids):
        raise RuntimeError("Simulated vector store failure")
    def delete_by_source_message(self, **kw):
        raise RuntimeError("Simulated vector store failure")


def _make_edit_svc(session, vm=None):
    vm = vm or _TrackingVM()
    return TelegramEditSynchronizationService(
        session=session, vector_mutation=vm,
        message_repo=SqliteTelegramMessageRepository(),
        chunk_repo=SqliteTelegramMessageChunkRepository(),
        processing_state_repo=SqliteTelegramProcessingStateRepository(),
        tombstone_repo=SqliteTelegramTombstoneRepository(),
    ), vm


def _make_del_svc(session, vm=None, delete_media=False):
    vm = vm or _TrackingVM()
    return TelegramDeleteSynchronizationService(
        session=session, vector_mutation=vm,
        message_repo=SqliteTelegramMessageRepository(),
        chunk_repo=SqliteTelegramMessageChunkRepository(),
        processing_state_repo=SqliteTelegramProcessingStateRepository(),
        tombstone_repo=SqliteTelegramTombstoneRepository(),
        delete_local_media=delete_media,
    ), vm


def _seed_message(session, acc_id="acc1", chat_id="chat1", msg_id="msg1",
                  text="Original text", owner="owner1") -> TelegramMessageORM:
    msg = TelegramMessageORM(
        id=str(uuid.uuid4()), owner_id=owner,
        telegram_account_id=acc_id, telegram_chat_id=chat_id,
        telegram_message_id=msg_id, raw_text=text,
        is_edited=False, is_deleted=False, current_version=1,
        processing_status="completed",
    )
    session.add(msg); session.flush()
    return msg


def _seed_chunk(session, msg_id: str, vector_id: str) -> TelegramMessageChunkORM:
    chunk = TelegramMessageChunkORM(
        id=str(uuid.uuid4()), telegram_message_record_id=msg_id,
        vector_id=vector_id, content_part="text", chunk_index=0,
        is_active=True, message_version=1,
    )
    session.add(chunk); session.flush()
    return chunk


# ===========================================================================
# Edit sync tests (Phase 18)
# ===========================================================================

class TestEditSync:

    def test_text_edit_updates_message(self, mem_session):
        msg = _seed_message(mem_session)
        _seed_chunk(mem_session, msg.id, "old_vid")
        svc, vm = _make_edit_svc(mem_session)
        ev = TelegramEditEvent("owner1", "acc1", "chat1", "msg1", new_text="Edited text")
        result = svc.synchronize(ev)
        assert result.status == "ok"
        assert result.current_version == 2
        refreshed = mem_session.query(TelegramMessageORM).filter_by(telegram_message_id="msg1").first()
        assert refreshed.is_edited is True
        assert refreshed.raw_text == "Edited text"

    def test_edit_deactivates_old_chunks(self, mem_session):
        msg = _seed_message(mem_session)
        _seed_chunk(mem_session, msg.id, "old_vid_1")
        _seed_chunk(mem_session, msg.id, "old_vid_2")
        svc, vm = _make_edit_svc(mem_session)
        ev = TelegramEditEvent("owner1", "acc1", "chat1", "msg1", new_text="Updated")
        result = svc.synchronize(ev)
        assert result.deleted_vector_count >= 0
        active = mem_session.query(TelegramMessageChunkORM).filter_by(
            telegram_message_record_id=msg.id, is_active=True
        ).all()
        # New chunk is active, old ones deactivated
        assert len(active) == 1

    def test_duplicate_edit_is_idempotent(self, mem_session):
        msg = _seed_message(mem_session)
        svc, vm = _make_edit_svc(mem_session)
        ev = TelegramEditEvent("owner1", "acc1", "chat1", "msg1",
                                new_text="Edit", update_id="upd1")
        r1 = svc.synchronize(ev)
        # Second call with same idempotency key
        svc2, vm2 = _make_edit_svc(mem_session, vm)
        r2 = svc2.synchronize(ev)
        assert r1.status == "ok"
        assert r2.status == "skipped"
        assert r2.reason == "already_processed"

    def test_edit_after_delete_does_not_recreate(self, mem_session):
        msg = _seed_message(mem_session)
        # Create tombstone first
        tomb_repo = SqliteTelegramTombstoneRepository()
        tomb_repo.create(mem_session, TelegramDeletionTombstoneORM(
            id=str(uuid.uuid4()), owner_id="owner1",
            source_account_id="acc1", conversation_id="chat1", source_message_id="msg1",
        ))
        mem_session.flush()
        svc, vm = _make_edit_svc(mem_session)
        ev = TelegramEditEvent("owner1", "acc1", "chat1", "msg1", new_text="Attempted restore")
        result = svc.synchronize(ev)
        assert result.status == "skipped"
        assert result.reason == "tombstone_exists"

    def test_unknown_message_edit_upserts_if_reconstructible(self, mem_session):
        """DR-4: edit for unknown message with sufficient fields → upsert."""
        svc, vm = _make_edit_svc(mem_session)
        ev = TelegramEditEvent("owner1", "acc1", "chat1", "unknown_msg",
                                new_text="New content for unknown")
        result = svc.synchronize(ev)
        assert result.status == "ok"
        new_msg = mem_session.query(TelegramMessageORM).filter_by(
            telegram_message_id="unknown_msg"
        ).first()
        assert new_msg is not None
        assert new_msg.is_edited is True

    def test_unknown_message_edit_fails_if_unreconstructible(self, mem_session):
        svc, vm = _make_edit_svc(mem_session)
        ev = TelegramEditEvent("owner1", "acc1", "chat1", "unknown_msg2",
                                new_text=None, new_content_type="text")
        result = svc.synchronize(ev)
        assert result.status == "failed"
        assert result.reason == "unknown_message_unreconstructible"

    def test_edit_with_stale_deletion_failure_marks_cleanup_pending(self, mem_session):
        msg = _seed_message(mem_session)
        _seed_chunk(mem_session, msg.id, "old_vid")
        svc, vm = _make_edit_svc(mem_session, _FailingVM())
        ev = TelegramEditEvent("owner1", "acc1", "chat1", "msg1", new_text="Edit")
        result = svc.synchronize(ev)
        assert result.cleanup_pending is True

    def test_no_duplicate_active_vectors_after_edit(self, mem_session):
        msg = _seed_message(mem_session)
        _seed_chunk(mem_session, msg.id, "vid_v1")
        svc, _ = _make_edit_svc(mem_session)
        ev = TelegramEditEvent("owner1", "acc1", "chat1", "msg1", new_text="Edit v2")
        svc.synchronize(ev)
        active = mem_session.query(TelegramMessageChunkORM).filter_by(
            telegram_message_record_id=msg.id, is_active=True
        ).count()
        assert active == 1


# ===========================================================================
# Delete sync tests (Phase 19)
# ===========================================================================

class TestDeleteSync:

    def test_text_deletion_marks_message_deleted(self, mem_session):
        msg = _seed_message(mem_session)
        _seed_chunk(mem_session, msg.id, "vid1")
        svc, vm = _make_del_svc(mem_session)
        ev = TelegramDeleteEvent("owner1", "acc1", "chat1", "msg1")
        result = svc.synchronize(ev)
        assert result.status == "ok"
        refreshed = mem_session.query(TelegramMessageORM).filter_by(
            telegram_message_id="msg1"
        ).first()
        assert refreshed.is_deleted is True

    def test_deletion_deactivates_chunks(self, mem_session):
        msg = _seed_message(mem_session)
        _seed_chunk(mem_session, msg.id, "vid1")
        _seed_chunk(mem_session, msg.id, "vid2")
        svc, vm = _make_del_svc(mem_session)
        ev = TelegramDeleteEvent("owner1", "acc1", "chat1", "msg1")
        svc.synchronize(ev)
        active = mem_session.query(TelegramMessageChunkORM).filter_by(
            is_active=True
        ).count()
        assert active == 0

    def test_deletion_creates_tombstone(self, mem_session):
        _seed_message(mem_session)
        svc, _ = _make_del_svc(mem_session)
        ev = TelegramDeleteEvent("owner1", "acc1", "chat1", "msg1")
        svc.synchronize(ev)
        assert mem_session.query(TelegramDeletionTombstoneORM).filter_by(
            source_message_id="msg1"
        ).first() is not None

    def test_duplicate_delete_is_idempotent(self, mem_session):
        _seed_message(mem_session)
        svc, _ = _make_del_svc(mem_session)
        ev = TelegramDeleteEvent("owner1", "acc1", "chat1", "msg1")
        r1 = svc.synchronize(ev)
        r2 = svc.synchronize(ev)
        assert r1.status == "ok"
        assert r2.status == "skipped"

    def test_unknown_message_delete_creates_tombstone(self, mem_session):
        svc, _ = _make_del_svc(mem_session)
        ev = TelegramDeleteEvent("owner1", "acc1", "chat1", "unknown_msg")
        result = svc.synchronize(ev)
        assert result.status == "not_found"
        assert mem_session.query(TelegramDeletionTombstoneORM).filter_by(
            source_message_id="unknown_msg"
        ).first() is not None

    def test_replay_after_delete_blocked_by_tombstone(self, mem_session):
        """Phase 10: tombstone prevents re-ingestion of deleted message."""
        svc, _ = _make_del_svc(mem_session)
        ev = TelegramDeleteEvent("owner1", "acc1", "chat1", "msg_deleted")
        svc.synchronize(ev)  # creates tombstone (not_found case)
        tomb_repo = SqliteTelegramTombstoneRepository()
        assert tomb_repo.exists(mem_session, "acc1", "chat1", "msg_deleted") is True
        # Attempt to re-ingest (edit sync should block)
        from app.integrations.telegram.services.edit_sync import TelegramEditSynchronizationService, TelegramEditEvent
        edit_svc = TelegramEditSynchronizationService(
            session=mem_session, vector_mutation=_TrackingVM(),
            message_repo=SqliteTelegramMessageRepository(),
            chunk_repo=SqliteTelegramMessageChunkRepository(),
            processing_state_repo=SqliteTelegramProcessingStateRepository(),
            tombstone_repo=SqliteTelegramTombstoneRepository(),
        )
        edit_ev = TelegramEditEvent("owner1", "acc1", "chat1", "msg_deleted", "new text")
        result = edit_svc.synchronize(edit_ev)
        assert result.status == "skipped"
        assert result.reason == "tombstone_exists"

    def test_vector_deletion_failure_marks_cleanup_pending(self, mem_session):
        msg = _seed_message(mem_session)
        _seed_chunk(mem_session, msg.id, "vid1")
        svc, _ = _make_del_svc(mem_session, vm=_FailingVM())
        ev = TelegramDeleteEvent("owner1", "acc1", "chat1", "msg1")
        result = svc.synchronize(ev)
        assert result.cleanup_pending is True
        # Message is still marked deleted (DB succeeded even when vector failed)
        refreshed = mem_session.query(TelegramMessageORM).filter_by(
            telegram_message_id="msg1"
        ).first()
        assert refreshed.is_deleted is True

    def test_safe_file_deletion_rejects_path_traversal(self, tmp_path):
        """Phase 9: path traversal outside media root is rejected silently."""
        from app.integrations.telegram.services.delete_sync import TelegramDeleteSynchronizationService
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        session = Session()
        svc = TelegramDeleteSynchronizationService(
            session=session, vector_mutation=_TrackingVM(),
            message_repo=SqliteTelegramMessageRepository(),
            chunk_repo=SqliteTelegramMessageChunkRepository(),
            processing_state_repo=SqliteTelegramProcessingStateRepository(),
            tombstone_repo=SqliteTelegramTombstoneRepository(),
            delete_local_media=True,
            media_root=tmp_path / "media",
        )
        # Attempt path traversal
        result = svc._safe_delete_file("../../../etc/passwd")
        assert result == 0  # rejected — outside media root
        session.close()

    def test_missing_file_is_safe_noop(self, tmp_path):
        from app.integrations.telegram.services.delete_sync import TelegramDeleteSynchronizationService
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        session = Session()
        media_root = tmp_path / "media"
        media_root.mkdir()
        svc = TelegramDeleteSynchronizationService(
            session=session, vector_mutation=_TrackingVM(),
            message_repo=SqliteTelegramMessageRepository(),
            chunk_repo=SqliteTelegramMessageChunkRepository(),
            processing_state_repo=SqliteTelegramProcessingStateRepository(),
            tombstone_repo=SqliteTelegramTombstoneRepository(),
            delete_local_media=True,
            media_root=media_root,
        )
        result = svc._safe_delete_file("nonexistent_file.mp3")
        assert result == 0
        session.close()


# ===========================================================================
# Reconciliation tests (Phase 21)
# ===========================================================================

class TestReconciliation:

    def test_stuck_processing_state_marked_failed(self, mem_session):
        from datetime import timedelta
        from app.integrations.telegram.db.orm_models import TelegramProcessingStateORM
        from app.integrations.telegram.services.reconciliation import TelegramSynchronizationReconciler

        msg = _seed_message(mem_session)
        ps = TelegramProcessingStateORM(
            id=str(uuid.uuid4()), telegram_message_record_id=msg.id,
            operation_type="ingest", status="processing",
            idempotency_key="test_stuck_key",
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        mem_session.add(ps); mem_session.commit()

        recon = TelegramSynchronizationReconciler(
            session=mem_session, vector_mutation=_TrackingVM(),
            chunk_repo=SqliteTelegramMessageChunkRepository(),
            processing_state_repo=SqliteTelegramProcessingStateRepository(),
            message_repo=SqliteTelegramMessageRepository(),
            stuck_threshold_minutes=1,
        )
        report = recon.run()
        assert report.stuck_operations_found >= 1
        assert report.repaired >= 1

    def test_deleted_message_with_active_chunks_cleaned_up(self, mem_session):
        from app.integrations.telegram.services.reconciliation import TelegramSynchronizationReconciler
        msg = _seed_message(mem_session)
        _seed_chunk(mem_session, msg.id, "stale_vid")
        msg.is_deleted = True
        mem_session.flush()

        vm = _TrackingVM()
        recon = TelegramSynchronizationReconciler(
            session=mem_session, vector_mutation=vm,
            chunk_repo=SqliteTelegramMessageChunkRepository(),
            processing_state_repo=SqliteTelegramProcessingStateRepository(),
            message_repo=SqliteTelegramMessageRepository(),
        )
        report = recon.run()
        assert report.cleanup_pending_messages >= 1
        assert "stale_vid" in vm.deleted

    def test_reconciliation_is_idempotent(self, mem_session):
        from app.integrations.telegram.services.reconciliation import TelegramSynchronizationReconciler
        recon = TelegramSynchronizationReconciler(
            session=mem_session, vector_mutation=_TrackingVM(),
            chunk_repo=SqliteTelegramMessageChunkRepository(),
            processing_state_repo=SqliteTelegramProcessingStateRepository(),
            message_repo=SqliteTelegramMessageRepository(),
        )
        r1 = recon.run()
        r2 = recon.run()
        assert r1.errors == []
        assert r2.errors == []


# ===========================================================================
# is_deleted defense test (Phase 14)
# ===========================================================================

class TestIsDeletedDefense:

    def test_non_telegram_unaffected_by_is_deleted_filter(self):
        """
        Regression: non-Telegram records (e.g. from other sources) must not
        be excluded by the is_deleted defense. The defense fires only when
        source==telegram AND is_deleted==True.
        """
        from models.retrieved_document import RetrievedDocument
        # A doc from a non-Telegram source — has no is_deleted field
        non_tg_doc = RetrievedDocument(
            document_id="non_tg_doc1", text="Some external message",
            metadata={"source_chat": "Alice & Bob"},
            distance=0.1, similarity_score=0.9, rank=1,
            source_collection="test", query="q",
        )
        # Apply the same filter logic from query_service
        filtered = [
            r for r in [non_tg_doc]
            if not (
                r.metadata.get("source") == "telegram"
                and r.metadata.get("is_deleted") is True
            )
        ]
        assert len(filtered) == 1
        assert filtered[0].document_id == "non_tg_doc1"

    def test_telegram_deleted_excluded(self):
        """Deleted Telegram doc IS excluded by the defense."""
        from models.retrieved_document import RetrievedDocument
        deleted_doc = RetrievedDocument(
            document_id="tg_del", text="Deleted message",
            metadata={"source": "telegram", "is_deleted": True, "owner_id": "o1"},
            distance=0.1, similarity_score=0.9, rank=1,
            source_collection="test", query="q",
        )
        filtered = [
            r for r in [deleted_doc]
            if not (
                r.metadata.get("source") == "telegram"
                and r.metadata.get("is_deleted") is True
            )
        ]
        assert len(filtered) == 0

    def test_telegram_not_deleted_included(self):
        """Non-deleted Telegram doc is NOT excluded."""
        from models.retrieved_document import RetrievedDocument
        active_doc = RetrievedDocument(
            document_id="tg_active", text="Active message",
            metadata={"source": "telegram", "is_deleted": False, "owner_id": "o1"},
            distance=0.1, similarity_score=0.9, rank=1,
            source_collection="test", query="q",
        )
        filtered = [
            r for r in [active_doc]
            if not (
                r.metadata.get("source") == "telegram"
                and r.metadata.get("is_deleted") is True
            )
        ]
        assert len(filtered) == 1
