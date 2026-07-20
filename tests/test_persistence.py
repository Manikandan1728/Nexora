"""
tests/test_persistence.py — Phase 1–4, 17: DB schema, repositories, ownership checker.
All tests use an in-memory SQLite database (no files created).
"""
from __future__ import annotations
import uuid
import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.integrations.telegram.db.orm_models import (
    Base, TelegramAccountORM, TelegramChatORM, TelegramMessageORM,
    TelegramMessageChunkORM, TelegramProcessingStateORM, TelegramDeletionTombstoneORM,
)
from app.integrations.telegram.repositories.account_repo import SqliteTelegramAccountRepository
from app.integrations.telegram.repositories.chat_repo import SqliteTelegramChatRepository
from app.integrations.telegram.repositories.message_repo import SqliteTelegramMessageRepository
from app.integrations.telegram.repositories.chunk_repo import SqliteTelegramMessageChunkRepository
from app.integrations.telegram.repositories.processing_state_repo import SqliteTelegramProcessingStateRepository
from app.integrations.telegram.repositories.tombstone_repo import SqliteTelegramTombstoneRepository
from app.integrations.telegram.services.ownership_checker import (
    DatabaseChatOwnershipChecker,
    TelegramConversationNotFoundError,
)


@pytest.fixture()
def mem_session():
    """In-memory SQLite session, fresh per test."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    yield session
    session.close()


def _account(owner="o1", tg_user="u1") -> TelegramAccountORM:
    return TelegramAccountORM(
        id=str(uuid.uuid4()), owner_id=owner,
        telegram_user_id=tg_user, is_active=True,
    )


def _chat(account_id: str, owner="o1", chat_id="c1", deleted=False) -> TelegramChatORM:
    return TelegramChatORM(
        id=str(uuid.uuid4()), owner_id=owner,
        telegram_account_id=account_id, telegram_chat_id=chat_id,
        is_deleted=deleted,
    )


def _msg(account_id: str, chat_id="c1", msg_id="m1", owner="o1") -> TelegramMessageORM:
    return TelegramMessageORM(
        id=str(uuid.uuid4()), owner_id=owner,
        telegram_account_id=account_id, telegram_chat_id=chat_id,
        telegram_message_id=msg_id,
    )


# ===========================================================================
# Schema smoke tests
# ===========================================================================

class TestSchemaCreation:
    def test_all_tables_exist(self, mem_session):
        from sqlalchemy import inspect
        inspector = inspect(mem_session.get_bind())
        tables = set(inspector.get_table_names())
        assert "tg_accounts" in tables
        assert "tg_chats" in tables
        assert "tg_messages" in tables
        assert "tg_attachments" in tables
        assert "tg_message_chunks" in tables
        assert "tg_processing_states" in tables
        assert "tg_deletion_tombstones" in tables

    def test_account_roundtrip(self, mem_session):
        acc = _account()
        mem_session.add(acc)
        mem_session.commit()
        row = mem_session.query(TelegramAccountORM).filter_by(owner_id="o1").first()
        assert row is not None
        assert row.telegram_user_id == "u1"

    def test_chat_fk_to_account(self, mem_session):
        acc = _account()
        mem_session.add(acc)
        mem_session.flush()
        chat = _chat(acc.id)
        mem_session.add(chat)
        mem_session.commit()
        assert mem_session.query(TelegramChatORM).count() == 1


# ===========================================================================
# Repository tests
# ===========================================================================

class TestChatRepository:
    def test_get_owned_chat_found(self, mem_session):
        acc = _account()
        mem_session.add(acc); mem_session.flush()
        chat = _chat(acc.id, chat_id="conv1")
        mem_session.add(chat); mem_session.commit()
        repo = SqliteTelegramChatRepository()
        result = repo.get_owned_chat(mem_session, "o1", "u1", "conv1")
        assert result is not None
        assert result.telegram_chat_id == "conv1"

    def test_get_owned_chat_wrong_owner(self, mem_session):
        acc = _account()
        mem_session.add(acc); mem_session.flush()
        mem_session.add(_chat(acc.id, owner="o1", chat_id="conv1"))
        mem_session.commit()
        repo = SqliteTelegramChatRepository()
        result = repo.get_owned_chat(mem_session, "o2", "u1", "conv1")
        assert result is None

    def test_get_owned_chat_deleted_excluded(self, mem_session):
        acc = _account()
        mem_session.add(acc); mem_session.flush()
        mem_session.add(_chat(acc.id, chat_id="conv1", deleted=True))
        mem_session.commit()
        repo = SqliteTelegramChatRepository()
        result = repo.get_owned_chat(mem_session, "o1", "u1", "conv1")
        assert result is None

    def test_get_owned_chats_mixed(self, mem_session):
        acc = _account()
        mem_session.add(acc); mem_session.flush()
        mem_session.add(_chat(acc.id, chat_id="conv1"))
        mem_session.add(_chat(acc.id, chat_id="conv2"))
        mem_session.commit()
        repo = SqliteTelegramChatRepository()
        results = repo.get_owned_chats(mem_session, "o1", "u1", ["conv1", "conv2"])
        assert len(results) == 2

    def test_upsert_no_duplicate(self, mem_session):
        acc = _account()
        mem_session.add(acc); mem_session.flush()
        repo = SqliteTelegramChatRepository()
        chat1 = _chat(acc.id, chat_id="c1")
        repo.upsert(mem_session, chat1)
        chat2 = _chat(acc.id, chat_id="c1")
        chat2.chat_title = "Updated"
        repo.upsert(mem_session, chat2)
        mem_session.commit()
        assert mem_session.query(TelegramChatORM).count() == 1


class TestMessageRepository:
    def test_upsert_new_message(self, mem_session):
        acc = _account()
        mem_session.add(acc); mem_session.flush()
        repo = SqliteTelegramMessageRepository()
        msg = _msg(acc.id)
        result = repo.upsert_new_message(mem_session, msg)
        mem_session.commit()
        assert result.id == msg.id

    def test_upsert_idempotent(self, mem_session):
        acc = _account()
        mem_session.add(acc); mem_session.flush()
        repo = SqliteTelegramMessageRepository()
        msg = _msg(acc.id)
        repo.upsert_new_message(mem_session, msg)
        msg2 = _msg(acc.id)  # same identity
        repo.upsert_new_message(mem_session, msg2)
        mem_session.commit()
        assert mem_session.query(TelegramMessageORM).count() == 1

    def test_mark_edited(self, mem_session):
        acc = _account()
        mem_session.add(acc); mem_session.flush()
        msg = _msg(acc.id)
        mem_session.add(msg); mem_session.flush()
        repo = SqliteTelegramMessageRepository()
        repo.mark_edited(mem_session, msg, "new text")
        mem_session.commit()
        refreshed = mem_session.query(TelegramMessageORM).first()
        assert refreshed.is_edited is True
        assert refreshed.current_version == 2
        assert refreshed.raw_text == "new text"

    def test_mark_deleted(self, mem_session):
        acc = _account()
        mem_session.add(acc); mem_session.flush()
        msg = _msg(acc.id)
        mem_session.add(msg); mem_session.flush()
        repo = SqliteTelegramMessageRepository()
        repo.mark_deleted(mem_session, msg)
        mem_session.commit()
        refreshed = mem_session.query(TelegramMessageORM).first()
        assert refreshed.is_deleted is True


class TestChunkRepository:
    def test_add_and_list_active(self, mem_session):
        acc = _account()
        mem_session.add(acc); mem_session.flush()
        msg = _msg(acc.id)
        mem_session.add(msg); mem_session.flush()
        chunk = TelegramMessageChunkORM(
            id=str(uuid.uuid4()), telegram_message_record_id=msg.id,
            vector_id="telegram:u1:c1:m1:text:0", content_part="text",
            chunk_index=0, is_active=True, message_version=1,
        )
        repo = SqliteTelegramMessageChunkRepository()
        repo.add_chunks(mem_session, [chunk])
        mem_session.commit()
        active = repo.list_active_chunks(mem_session, msg.id)
        assert len(active) == 1
        assert active[0].vector_id == "telegram:u1:c1:m1:text:0"

    def test_deactivate_chunks_returns_vector_ids(self, mem_session):
        acc = _account()
        mem_session.add(acc); mem_session.flush()
        msg = _msg(acc.id)
        mem_session.add(msg); mem_session.flush()
        chunk = TelegramMessageChunkORM(
            id=str(uuid.uuid4()), telegram_message_record_id=msg.id,
            vector_id="vid1", content_part="text", chunk_index=0,
            is_active=True, message_version=1,
        )
        repo = SqliteTelegramMessageChunkRepository()
        repo.add_chunks(mem_session, [chunk])
        mem_session.flush()
        deactivated = repo.deactivate_chunks(mem_session, msg.id)
        mem_session.commit()
        assert "vid1" in deactivated
        assert len(repo.list_active_chunks(mem_session, msg.id)) == 0


class TestTombstoneRepository:
    def test_exists_false_initially(self, mem_session):
        repo = SqliteTelegramTombstoneRepository()
        assert repo.exists(mem_session, "acc1", "conv1", "msg1") is False

    def test_exists_true_after_create(self, mem_session):
        repo = SqliteTelegramTombstoneRepository()
        t = TelegramDeletionTombstoneORM(
            id=str(uuid.uuid4()), owner_id="o1",
            source_account_id="acc1", conversation_id="conv1",
            source_message_id="msg1",
        )
        repo.create(mem_session, t)
        mem_session.commit()
        assert repo.exists(mem_session, "acc1", "conv1", "msg1") is True

    def test_create_idempotent(self, mem_session):
        repo = SqliteTelegramTombstoneRepository()
        t = TelegramDeletionTombstoneORM(
            id=str(uuid.uuid4()), owner_id="o1",
            source_account_id="acc1", conversation_id="conv1", source_message_id="msg1",
        )
        repo.create(mem_session, t)
        t2 = TelegramDeletionTombstoneORM(
            id=str(uuid.uuid4()), owner_id="o1",
            source_account_id="acc1", conversation_id="conv1", source_message_id="msg1",
        )
        repo.create(mem_session, t2)
        mem_session.commit()
        assert mem_session.query(TelegramDeletionTombstoneORM).count() == 1


# ===========================================================================
# Ownership checker tests (Phase 17)
# ===========================================================================

class TestDatabaseChatOwnershipChecker:
    def _setup_chat(self, session, owner, chat_id, deleted=False):
        acc = TelegramAccountORM(id=str(uuid.uuid4()), owner_id=owner,
                                  telegram_user_id=f"u_{owner}", is_active=True)
        session.add(acc); session.flush()
        chat = TelegramChatORM(id=str(uuid.uuid4()), owner_id=owner,
                                telegram_account_id=acc.id, telegram_chat_id=chat_id,
                                is_deleted=deleted)
        session.add(chat); session.flush()
        return acc, chat

    def test_owned_private_chat(self, mem_session):
        self._setup_chat(mem_session, "owner1", "conv_private")
        checker = DatabaseChatOwnershipChecker(mem_session)
        assert checker.is_owned("owner1", "conv_private") is True

    def test_owned_group_chat(self, mem_session):
        acc = TelegramAccountORM(id=str(uuid.uuid4()), owner_id="o1",
                                  telegram_user_id="u1", is_active=True)
        mem_session.add(acc); mem_session.flush()
        chat = TelegramChatORM(id=str(uuid.uuid4()), owner_id="o1",
                                telegram_account_id=acc.id, telegram_chat_id="group1",
                                chat_type="group", is_deleted=False)
        mem_session.add(chat); mem_session.flush()
        checker = DatabaseChatOwnershipChecker(mem_session)
        assert checker.is_owned("o1", "group1") is True

    def test_unknown_chat_returns_false(self, mem_session):
        checker = DatabaseChatOwnershipChecker(mem_session)
        assert checker.is_owned("o1", "unknown_conv") is False

    def test_cross_owner_chat_returns_false(self, mem_session):
        self._setup_chat(mem_session, "owner1", "conv_x")
        checker = DatabaseChatOwnershipChecker(mem_session)
        assert checker.is_owned("owner2", "conv_x") is False

    def test_deleted_chat_returns_false(self, mem_session):
        self._setup_chat(mem_session, "owner1", "conv_del", deleted=True)
        checker = DatabaseChatOwnershipChecker(mem_session)
        assert checker.is_owned("owner1", "conv_del") is False

    def test_same_chat_id_different_owners_isolated(self, mem_session):
        """Same telegram_chat_id under different owners must be isolated."""
        acc1 = TelegramAccountORM(id=str(uuid.uuid4()), owner_id="o1",
                                   telegram_user_id="u1", is_active=True)
        acc2 = TelegramAccountORM(id=str(uuid.uuid4()), owner_id="o2",
                                   telegram_user_id="u2", is_active=True)
        mem_session.add(acc1); mem_session.add(acc2); mem_session.flush()
        chat1 = TelegramChatORM(id=str(uuid.uuid4()), owner_id="o1",
                                 telegram_account_id=acc1.id, telegram_chat_id="shared_id",
                                 is_deleted=False)
        mem_session.add(chat1); mem_session.flush()
        checker = DatabaseChatOwnershipChecker(mem_session)
        assert checker.is_owned("o1", "shared_id") is True
        assert checker.is_owned("o2", "shared_id") is False

    def test_disabled_indexing_still_searchable(self, mem_session):
        """DR-1: indexing_enabled=False chat is still considered owned/searchable."""
        acc = TelegramAccountORM(id=str(uuid.uuid4()), owner_id="o1",
                                  telegram_user_id="u1", is_active=True)
        mem_session.add(acc); mem_session.flush()
        chat = TelegramChatORM(id=str(uuid.uuid4()), owner_id="o1",
                                telegram_account_id=acc.id, telegram_chat_id="disabled_chat",
                                indexing_enabled=False, is_deleted=False)
        mem_session.add(chat); mem_session.flush()
        checker = DatabaseChatOwnershipChecker(mem_session)
        assert checker.is_owned("o1", "disabled_chat") is True

    def test_mixed_authorized_unauthorized_list(self, mem_session):
        """All-or-nothing: if one conv is unauthorized, the whole query fails."""
        from app.retrieval.telegram_filter import (
            QueryScopeBuilder, TelegramMetadataFilter, ConversationNotOwned
        )
        acc = TelegramAccountORM(id=str(uuid.uuid4()), owner_id="o1",
                                  telegram_user_id="u1", is_active=True)
        mem_session.add(acc); mem_session.flush()
        chat = TelegramChatORM(id=str(uuid.uuid4()), owner_id="o1",
                                telegram_account_id=acc.id, telegram_chat_id="authorized",
                                is_deleted=False)
        mem_session.add(chat); mem_session.flush()
        checker = DatabaseChatOwnershipChecker(mem_session)
        scope = QueryScopeBuilder(ownership_checker=checker)
        tg_filter = TelegramMetadataFilter(
            conversation_ids=["authorized", "unauthorized_conv"]
        )
        tg_filter.validate()
        with pytest.raises(ConversationNotOwned):
            scope.build("o1", tg_filter)

    def test_frontend_owner_id_overridden(self, mem_session):
        """Client-supplied owner_id is always overridden by authenticated owner."""
        from app.retrieval.telegram_filter import QueryScopeBuilder, TelegramMetadataFilter
        checker = DatabaseChatOwnershipChecker(mem_session)
        scope = QueryScopeBuilder(ownership_checker=checker)
        tg_filter = TelegramMetadataFilter(owner_id="attacker_owner")
        tg_filter.validate()
        effective = scope.build("real_owner", tg_filter)
        assert effective.owner_id == "real_owner"
