"""
tests/test_phase_telegram.py — Phase 3–15 Telegram integration tests.

Covers spec §18 test requirements:
  - Domain tests (KnowledgeObject)
  - Normalizer tests (all fixture types)
  - Policy tests (enabled/disabled/before activation/duplicate/delete)
  - Deduplication tests (stable IDs, no duplicate vectors)
  - Client tests (MockTelegramClient behavior)
  - API tests (Telegram endpoints)
  - Regression tests (pre-existing vector IDs unaffected)

All tests are self-contained. No live Telegram, no real ChromaDB writes,
no model loading.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "telegram"


# ===========================================================================
# Helpers
# ===========================================================================

def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _make_owner() -> str:
    return "user_test_123"


def _activation_ts() -> datetime:
    """Activation time used in policy tests: 2026-07-13T18:00 IST = 12:30 UTC."""
    return datetime(2026, 7, 13, 12, 30, tzinfo=timezone.utc)


# ===========================================================================
# 1. Domain tests — KnowledgeObject
# ===========================================================================

class TestKnowledgeObject:

    def _make(self, **overrides):
        from models.knowledge_object import KnowledgeObject
        defaults = dict(
            owner_id="user_123",
            source="telegram",
            source_account_id="tg_account_001",
            conversation_id="tg_chat_anu_001",
            source_message_id="tg_message_1001",
            content_type="text",
            text="Hello world",
            timestamp=datetime(2026, 7, 13, 13, 0, tzinfo=timezone.utc),
        )
        defaults.update(overrides)
        return KnowledgeObject(**defaults)

    def test_valid_creation(self):
        obj = self._make()
        assert obj.owner_id == "user_123"
        assert obj.source == "telegram"
        assert obj.has_text is True

    def test_stable_id_format(self):
        obj = self._make()
        assert obj.stable_id == "telegram:tg_account_001:tg_chat_anu_001:tg_message_1001"

    def test_vector_document_id_format(self):
        obj = self._make()
        vid = obj.vector_document_id("pdf", 3)
        assert vid == "telegram:tg_account_001:tg_chat_anu_001:tg_message_1001:pdf:3"

    def test_vector_document_id_default(self):
        obj = self._make()
        vid = obj.vector_document_id()
        assert vid == "telegram:tg_account_001:tg_chat_anu_001:tg_message_1001:text:0"

    def test_has_text_false_when_empty(self):
        obj = self._make(text=None)
        assert obj.has_text is False

    def test_has_attachment_true_with_filename(self):
        obj = self._make(filename="file.pdf")
        assert obj.has_attachment is True

    def test_is_indexable_true_for_normal_message(self):
        obj = self._make()
        assert obj.is_indexable is True

    def test_is_indexable_false_when_deleted(self):
        obj = self._make(is_deleted=True)
        assert obj.is_indexable is False

    def test_is_indexable_false_when_before_activation(self):
        from models.knowledge_object import KnowledgeObject
        activation = datetime(2026, 7, 13, 14, 0, tzinfo=timezone.utc)
        obj = self._make(
            timestamp=datetime(2026, 7, 13, 13, 0, tzinfo=timezone.utc),
            indexing_enabled_at=activation,
        )
        assert obj.is_indexable is False

    def test_is_indexable_true_at_activation_boundary(self):
        activation = datetime(2026, 7, 13, 13, 0, tzinfo=timezone.utc)
        obj = self._make(
            timestamp=datetime(2026, 7, 13, 13, 0, tzinfo=timezone.utc),
            indexing_enabled_at=activation,
        )
        assert obj.is_indexable is True

    def test_is_indexable_false_no_text_no_attachment(self):
        obj = self._make(text=None, filename=None, file_path=None)
        assert obj.is_indexable is False

    def test_supported_content_types(self):
        from models.knowledge_object import SUPPORTED_CONTENT_TYPES, is_supported_content_type
        for ct in ["text", "link", "pdf", "docx", "pptx", "image", "voice", "video"]:
            assert is_supported_content_type(ct)
        assert not is_supported_content_type("unknown_type_xyz")


# ===========================================================================
# 2. Normalizer tests
# ===========================================================================

class TestTelegramNormalizer:

    def _norm(self):
        from app.integrations.telegram.mapping.telegram_normalizer import TelegramNormalizer
        return TelegramNormalizer()

    def test_text_message_produces_one_object(self):
        event = _load_fixture("text_message.json")
        objects = self._norm().normalize(event, owner_id=_make_owner())
        assert len(objects) == 1
        obj = objects[0]
        assert obj.content_type == "text"
        assert obj.source == "telegram"
        assert obj.conversation_id == "tg_chat_anu_001"
        assert obj.sender_id == "tg_user_anu_001"
        assert obj.sender_name == "Anu"
        assert obj.text == "The project report must be submitted before Monday."

    def test_link_message_detected(self):
        event = _load_fixture("link_message.json")
        objects = self._norm().normalize(event, owner_id=_make_owner())
        assert len(objects) == 1
        assert objects[0].content_type == "link"

    def test_pdf_message_produces_two_objects(self):
        event = _load_fixture("pdf_message.json")
        objects = self._norm().normalize(event, owner_id=_make_owner())
        # text caption + attachment
        assert len(objects) == 2
        types = {o.content_type for o in objects}
        assert "text" in types or "link" in types
        assert "pdf" in types

    def test_image_with_caption_produces_two_objects(self):
        event = _load_fixture("image_with_caption.json")
        objects = self._norm().normalize(event, owner_id=_make_owner())
        assert len(objects) == 2

    def test_image_without_caption_produces_one_object(self):
        event = _load_fixture("image_without_caption.json")
        objects = self._norm().normalize(event, owner_id=_make_owner())
        assert len(objects) == 1
        assert objects[0].content_type == "image"

    def test_voice_message_produces_one_object(self):
        event = _load_fixture("voice_message.json")
        objects = self._norm().normalize(event, owner_id=_make_owner())
        assert len(objects) == 1
        assert objects[0].content_type == "voice"

    def test_reply_message_preserves_reply_id(self):
        event = _load_fixture("reply_message.json")
        objects = self._norm().normalize(event, owner_id=_make_owner())
        assert len(objects) == 1
        assert objects[0].reply_to_message_id == "tg_message_1001"

    def test_forwarded_message_preserves_forwarded_from(self):
        event = _load_fixture("forwarded_message.json")
        objects = self._norm().normalize(event, owner_id=_make_owner())
        assert objects[0].forwarded_from == "Department Head"

    def test_edited_message_sets_is_edited(self):
        event = _load_fixture("edited_message.json")
        objects = self._norm().normalize(event, owner_id=_make_owner())
        assert all(o.is_edited for o in objects)

    def test_deleted_message_sets_is_deleted(self):
        event = _load_fixture("deleted_message.json")
        objects = self._norm().normalize(event, owner_id=_make_owner())
        assert len(objects) == 1
        assert objects[0].is_deleted is True
        assert objects[0].content_type == "system"

    def test_group_message_captures_chat_id(self):
        event = _load_fixture("group_message.json")
        objects = self._norm().normalize(event, owner_id=_make_owner())
        assert objects[0].conversation_id == "tg_group_project_001"
        assert objects[0].sender_id == "tg_user_anu_001"

    def test_docx_message_content_type(self):
        event = _load_fixture("docx_message.json")
        objects = self._norm().normalize(event, owner_id=_make_owner())
        types = {o.content_type for o in objects}
        assert "docx" in types

    def test_pptx_message_content_type(self):
        event = _load_fixture("pptx_message.json")
        objects = self._norm().normalize(event, owner_id=_make_owner())
        types = {o.content_type for o in objects}
        assert "pptx" in types

    def test_owner_id_set_from_parameter(self):
        event = _load_fixture("text_message.json")
        objects = self._norm().normalize(event, owner_id="specific_owner")
        assert all(o.owner_id == "specific_owner" for o in objects)

    def test_missing_account_id_returns_empty(self):
        event = {"chat_id": "c1", "message_id": "m1", "message_type": "text",
                 "text": "hi", "timestamp": "2026-07-13T18:30:00+05:30"}
        objects = self._norm().normalize(event, owner_id="u1")
        assert objects == []

    def test_invalid_timestamp_returns_empty(self):
        event = _load_fixture("text_message.json")
        event = dict(event, timestamp="not-a-date")
        objects = self._norm().normalize(event, owner_id="u1")
        assert objects == []

    def test_indexing_enabled_at_propagated(self):
        event = _load_fixture("text_message.json")
        activation = _activation_ts()
        objects = self._norm().normalize(event, owner_id=_make_owner(),
                                          indexing_enabled_at=activation)
        assert all(o.indexing_enabled_at == activation for o in objects)


# ===========================================================================
# 3. Policy tests — TelegramIngestionPolicy
# ===========================================================================

class _EnabledConfig:
    """Stub: indexing enabled for chat_anu_001 and group_project_001."""
    def is_indexing_enabled(self, owner_id, conversation_id):
        return conversation_id not in ("tg_chat_disabled_001",)

    def get_indexing_enabled_at(self, owner_id, conversation_id):
        return _activation_ts()

    def is_account_owner(self, owner_id, source_account_id):
        return True


class _NeverProcessed:
    def is_already_processed(self, account_id, conv_id, msg_id):
        return False


class _AlwaysProcessed:
    def is_already_processed(self, account_id, conv_id, msg_id):
        return True


def _make_policy(config=None, state=None):
    from app.integrations.telegram.services.ingestion_policy import TelegramIngestionPolicy
    return TelegramIngestionPolicy(
        config_provider=config or _EnabledConfig(),
        state_provider=state or _NeverProcessed(),
    )


def _norm_first(fixture_name: str, owner: str = "user_123",
                activation=None) -> Any:
    from app.integrations.telegram.mapping.telegram_normalizer import TelegramNormalizer
    event = _load_fixture(fixture_name)
    objs = TelegramNormalizer().normalize(event, owner_id=owner,
                                          indexing_enabled_at=activation or _activation_ts())
    return objs[0] if objs else None


class TestIngestionPolicy:

    def test_enabled_chat_after_activation_returns_process(self):
        from app.integrations.telegram.services.ingestion_policy import IngestionAction
        obj = _norm_first("text_message.json")
        decision = _make_policy().decide(obj)
        assert decision.action == IngestionAction.PROCESS

    def test_disabled_chat_returns_ignore(self):
        from app.integrations.telegram.services.ingestion_policy import IngestionAction
        obj = _norm_first("disabled_chat_message.json")
        decision = _make_policy().decide(obj)
        assert decision.action == IngestionAction.IGNORE
        assert "disabled" in decision.reason.lower()

    def test_before_activation_returns_ignore(self):
        from app.integrations.telegram.services.ingestion_policy import IngestionAction
        obj = _norm_first("before_activation_message.json")
        assert obj is not None
        decision = _make_policy().decide(obj)
        assert decision.action == IngestionAction.IGNORE
        assert "before" in decision.reason.lower()

    def test_deleted_message_returns_process_delete(self):
        from app.integrations.telegram.services.ingestion_policy import IngestionAction
        obj = _norm_first("deleted_message.json")
        decision = _make_policy().decide(obj)
        assert decision.action == IngestionAction.PROCESS_DELETE

    def test_edited_message_returns_process_edit(self):
        from app.integrations.telegram.services.ingestion_policy import IngestionAction
        obj = _norm_first("edited_message.json")
        decision = _make_policy().decide(obj)
        assert decision.action == IngestionAction.PROCESS_EDIT

    def test_duplicate_message_returns_ignore(self):
        from app.integrations.telegram.services.ingestion_policy import IngestionAction
        obj = _norm_first("text_message.json")
        decision = _make_policy(state=_AlwaysProcessed()).decide(obj)
        assert decision.action == IngestionAction.IGNORE
        assert "idempotency" in decision.reason.lower()

    def test_wrong_owner_returns_ignore(self):
        from app.integrations.telegram.services.ingestion_policy import IngestionAction

        class _WrongOwner:
            def is_indexing_enabled(self, o, c): return True
            def get_indexing_enabled_at(self, o, c): return None
            def is_account_owner(self, owner_id, account_id): return False

        obj = _norm_first("text_message.json")
        decision = _make_policy(config=_WrongOwner()).decide(obj)
        assert decision.action == IngestionAction.IGNORE

    def test_decision_has_reason(self):
        obj = _norm_first("text_message.json")
        decision = _make_policy().decide(obj)
        assert isinstance(decision.reason, str)
        assert len(decision.reason) > 0

    def test_should_process_true_for_process(self):
        from app.integrations.telegram.services.ingestion_policy import IngestionAction, IngestionDecision
        d = IngestionDecision(action=IngestionAction.PROCESS, reason="ok")
        assert d.should_process is True
        assert d.should_ignore is False

    def test_should_ignore_true_for_ignore(self):
        from app.integrations.telegram.services.ingestion_policy import IngestionAction, IngestionDecision
        d = IngestionDecision(action=IngestionAction.IGNORE, reason="off")
        assert d.should_ignore is True
        assert d.should_process is False


# ===========================================================================
# 4. Deduplication tests
# ===========================================================================

class TestDeduplication:

    def _make_dedup(self):
        from app.integrations.telegram.services.deduplication_service import (
            TelegramDeduplicationService, InMemoryProcessedMessageStore,
        )
        return TelegramDeduplicationService(InMemoryProcessedMessageStore())

    def _make_obj(self, msg_id="tg_message_1001"):
        from models.knowledge_object import KnowledgeObject
        return KnowledgeObject(
            owner_id="user_123",
            source="telegram",
            source_account_id="tg_account_001",
            conversation_id="tg_chat_anu_001",
            source_message_id=msg_id,
            content_type="text",
            text="hello",
            timestamp=datetime(2026, 7, 13, 13, 0, tzinfo=timezone.utc),
        )

    def test_stable_vector_id_format(self):
        dedup = self._make_dedup()
        obj = self._make_obj()
        vid = dedup.vector_id(obj, "text", 0)
        assert vid == "telegram:tg_account_001:tg_chat_anu_001:tg_message_1001:text:0"

    def test_stable_id_deterministic(self):
        dedup = self._make_dedup()
        obj = self._make_obj()
        assert dedup.vector_id(obj, "pdf", 2) == dedup.vector_id(obj, "pdf", 2)

    def test_not_duplicate_before_marking(self):
        dedup = self._make_dedup()
        obj = self._make_obj()
        vid = dedup.vector_id(obj)
        assert dedup.is_duplicate(vid) is False

    def test_duplicate_after_marking(self):
        dedup = self._make_dedup()
        obj = self._make_obj()
        vid = dedup.vector_id(obj)
        dedup.mark_processed(vid)
        assert dedup.is_duplicate(vid) is True

    def test_different_message_ids_not_duplicate(self):
        dedup = self._make_dedup()
        obj1 = self._make_obj("tg_message_1001")
        obj2 = self._make_obj("tg_message_1002")
        vid1 = dedup.vector_id(obj1)
        vid2 = dedup.vector_id(obj2)
        dedup.mark_processed(vid1)
        assert dedup.is_duplicate(vid2) is False

    def test_remove_allows_reprocessing(self):
        dedup = self._make_dedup()
        obj = self._make_obj()
        vid = dedup.vector_id(obj)
        dedup.mark_processed(vid)
        dedup.remove(vid)
        assert dedup.is_duplicate(vid) is False

    def test_non_telegram_ids_unaffected(self):
        """Regression: non-Telegram vector IDs are unaffected by this service."""
        dedup = self._make_dedup()
        non_telegram_id = "3f4e5a6b-1234-abcd-efgh-000000000001"
        assert dedup.is_duplicate(non_telegram_id) is False
        dedup.mark_processed(non_telegram_id)
        assert dedup.is_duplicate(non_telegram_id) is True
        # Marking one ID doesn't affect others
        other_id = "3f4e5a6b-1234-abcd-efgh-000000000002"
        assert dedup.is_duplicate(other_id) is False

    def test_duplicate_update_does_not_create_duplicate_if_policy_enforced(self):
        """Processing same event twice is safe when policy + dedup are used together."""
        from app.integrations.telegram.mapping.telegram_normalizer import TelegramNormalizer
        from app.integrations.telegram.services.ingestion_policy import (
            TelegramIngestionPolicy, IngestionAction
        )
        from app.integrations.telegram.services.deduplication_service import (
            TelegramDeduplicationService, InMemoryProcessedMessageStore
        )

        store = InMemoryProcessedMessageStore()
        dedup = TelegramDeduplicationService(store)
        norm = TelegramNormalizer()

        class _EnabledAndTracked:
            def __init__(self):
                self._processed = set()
            def is_indexing_enabled(self, o, c): return True
            def get_indexing_enabled_at(self, o, c): return _activation_ts()
            def is_account_owner(self, o, a): return True
            def is_already_processed(self, a, c, m):
                return (a, c, m) in self._processed
            def mark(self, a, c, m):
                self._processed.add((a, c, m))

        config_state = _EnabledAndTracked()
        policy = TelegramIngestionPolicy(
            config_provider=config_state, state_provider=config_state
        )

        event = _load_fixture("text_message.json")
        indexed_count = 0

        for _ in range(2):  # process same event twice
            objects = norm.normalize(event, owner_id="user_123",
                                     indexing_enabled_at=_activation_ts())
            for obj in objects:
                decision = policy.decide(obj)
                if decision.action == IngestionAction.PROCESS:
                    vid = dedup.vector_id(obj)
                    if not dedup.is_duplicate(vid):
                        indexed_count += 1
                        dedup.mark_processed(vid)
                        config_state.mark(
                            obj.source_account_id,
                            obj.conversation_id,
                            obj.source_message_id,
                        )

        assert indexed_count == 1, f"Expected 1 indexed, got {indexed_count}"


# ===========================================================================
# 5. MockTelegramClient tests
# ===========================================================================

class TestMockTelegramClient:

    def _client(self, fixtures_dir=None):
        from app.integrations.telegram.client.mock_telegram_client import MockTelegramClientGateway
        return MockTelegramClientGateway(fixtures_dir=fixtures_dir or FIXTURES_DIR)

    @pytest.mark.asyncio
    async def test_initial_state_disconnected(self):
        from app.integrations.telegram.client.mock_telegram_client import MockTelegramClientGateway
        client = MockTelegramClientGateway(auth_state="disconnected")
        state = await client.is_authorized()
        assert state is False

    @pytest.mark.asyncio
    async def test_connect_transitions_connected(self):
        client = self._client()
        await client.connect()
        client._auth_state = "ready"
        assert await client.is_authorized() is True

    @pytest.mark.asyncio
    async def test_submit_phone_transitions_to_waiting_code(self):
        client = self._client()
        await client.connect()
        res = await client.start_authentication("+91XXXXXXXXXX")
        assert res["status"] == "code_sent"
        assert client._auth_state == "waiting_code"

    @pytest.mark.asyncio
    async def test_submit_code_transitions_to_ready(self):
        client = self._client()
        await client.connect()
        await client.start_authentication("+91XXXXXXXXXX")
        res = await client.verify_code("12345")
        assert res is True
        assert client._auth_state == "ready"

    @pytest.mark.asyncio
    async def test_disconnect_transitions_to_closed(self):
        client = self._client()
        await client.connect()
        await client.log_out()
        assert await client.is_authorized() is False
        assert client._connected is False

    @pytest.mark.asyncio
    async def test_list_chats_returns_chats(self):
        client = self._client()
        await client.connect()
        chats = await client.list_chats()
        assert isinstance(chats, list)
        assert len(chats) >= 1
        assert all("chat_id" in c for c in chats)

    @pytest.mark.asyncio
    async def test_updates_yields_fixture_events(self):
        client = self._client()
        await client.connect()
        events = []
        async for event in client.updates():
            events.append(event)
        # Should yield at least some events (non-comment fixtures)
        assert len(events) >= 5

    @pytest.mark.asyncio
    async def test_download_file_returns_path(self):
        client = self._client()
        path = await client.download_file("tg_file_pdf_001")
        assert "tg_file_pdf_001" in path

    @pytest.mark.asyncio
    async def test_updates_no_crash_on_missing_fixtures_dir(self, tmp_path):
        from app.integrations.telegram.client.mock_telegram_client import MockTelegramClientGateway
        client = MockTelegramClientGateway(fixtures_dir=tmp_path / "nonexistent")
        await client.connect()
        events = []
        async for event in client.updates():
            events.append(event)
        assert events == []


# ===========================================================================
# 6. ContentTypeMapper tests
# ===========================================================================

class TestContentTypeMapper:

    def _mapper(self):
        from app.integrations.telegram.mapping.content_type_mapper import ContentTypeMapper
        return ContentTypeMapper()

    def test_text_maps_to_text(self):
        assert self._mapper().map("text") == "text"

    def test_photo_maps_to_image(self):
        assert self._mapper().map("photo") == "image"

    def test_voice_maps_to_voice(self):
        assert self._mapper().map("voice") == "voice"

    def test_document_with_pdf_mime(self):
        assert self._mapper().map("document", "application/pdf") == "pdf"

    def test_document_with_docx_mime(self):
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        assert self._mapper().map("document", mime) == "docx"

    def test_document_with_pptx_mime(self):
        mime = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        assert self._mapper().map("document", mime) == "pptx"

    def test_document_unknown_mime_falls_back_to_document(self):
        assert self._mapper().map("document", "application/octet-stream") == "document"

    def test_video_maps_to_video(self):
        assert self._mapper().map("video") == "video"

    def test_unknown_type_falls_back_to_document(self):
        assert self._mapper().map("something_new") == "document"


# ===========================================================================
# 7. Telegram model tests
# ===========================================================================

class TestTelegramModels:

    def test_telegram_account_defaults(self):
        from app.integrations.telegram.models.telegram_models import (
            TelegramAccount, AuthorizationStatus
        )
        acc = TelegramAccount(owner_id="u1", telegram_user_id="tg123")
        assert acc.authorization_status == AuthorizationStatus.DISCONNECTED
        assert acc.id  # UUID generated

    def test_telegram_chat_defaults(self):
        from app.integrations.telegram.models.telegram_models import TelegramChat
        chat = TelegramChat(
            owner_id="u1",
            telegram_account_id="acc1",
            telegram_chat_id="chat1",
        )
        assert chat.indexing_enabled is False
        assert chat.indexing_enabled_at is None

    def test_telegram_message_defaults(self):
        from app.integrations.telegram.models.telegram_models import (
            TelegramMessage, ProcessingStatus
        )
        msg = TelegramMessage(
            owner_id="u1",
            telegram_account_id="acc1",
            telegram_chat_id="chat1",
            telegram_message_id="msg1",
        )
        assert msg.is_edited is False
        assert msg.is_deleted is False
        assert msg.processing_status == ProcessingStatus.PENDING

    def test_telegram_attachment_defaults(self):
        from app.integrations.telegram.models.telegram_models import (
            TelegramAttachment, DownloadStatus
        )
        att = TelegramAttachment(
            telegram_message_record_id="rec1",
            telegram_file_id="file1",
        )
        assert att.download_status == DownloadStatus.PENDING
        assert att.checksum is None


# ===========================================================================
# 8. API endpoint tests (Telegram routes)
# ===========================================================================

class TestTelegramAPIRoutes:

    @pytest.fixture()
    def client(self, test_settings):
        from fastapi.testclient import TestClient
        from api.config import get_settings
        from api.dependencies import get_db_session
        from api.main import create_app
        from app.integrations.telegram.db.orm_models import Base
        from sqlalchemy import create_engine, StaticPool
        from sqlalchemy.orm import sessionmaker

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        
        def override_get_db_session():
            session = sessionmaker(bind=engine)()
            try:
                yield session
            finally:
                session.close()

        app = create_app()
        app.dependency_overrides[get_settings] = lambda: test_settings
        app.dependency_overrides[get_db_session] = override_get_db_session
        
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c

    def test_status_endpoint_returns_200(self, client):
        r = client.get("/integrations/telegram/status?owner_id=user_123")
        assert r.status_code == 200
        data = r.json()
        assert "authorization_status" in data

    def test_connect_returns_waiting_phone(self, client):
        r = client.post("/integrations/telegram/connect",
                        json={"owner_id": "user_123"})
        assert r.status_code == 200
        assert r.json()["authorization_status"] == "waiting_phone"

    def test_submit_phone_transitions_to_waiting_code(self, client):
        client.post("/integrations/telegram/connect", json={"owner_id": "u1"})
        r = client.post("/integrations/telegram/auth/phone",
                        json={"owner_id": "u1", "phone_number": "+910000000000"})
        assert r.status_code == 200
        assert r.json()["status"] == "waiting_code"

    def test_submit_code_transitions_to_ready(self, client):
        client.post("/integrations/telegram/connect", json={"owner_id": "u1"})
        res = client.post("/integrations/telegram/auth/phone",
                    json={"owner_id": "u1", "phone_number": "+910000000000"})
        attempt_id = res.json().get("authentication_attempt_id", "mock")
        r = client.post("/integrations/telegram/auth/code", json={"owner_id": "u1", "attempt_id": attempt_id, "code": "12345"})
        assert r.status_code == 200
        assert r.json()["authorization_status"] == "ready"

    def test_list_chats_returns_chats(self, client):
        r = client.get("/integrations/telegram/chats")
        assert r.status_code == 200
        data = r.json()
        assert "chats" in data
        assert data["total"] >= 1

    def test_get_chat_known_id(self, client):
        r = client.get("/integrations/telegram/chats/tg_chat_anu_001")
        assert r.status_code == 200
        assert r.json()["chat_id"] == "tg_chat_anu_001"

    def test_get_chat_unknown_id_returns_404(self, client):
        r = client.get("/integrations/telegram/chats/nonexistent_chat")
        assert r.status_code == 404

    def test_update_chat_enable_indexing(self, client):
        r = client.patch("/integrations/telegram/chats/tg_chat_anu_001",
                         json={"indexing_enabled": True})
        assert r.status_code == 200
        assert r.json()["indexing_enabled"] is True

    def test_delete_chat_data(self, client):
        r = client.delete("/integrations/telegram/chats/tg_chat_anu_001/data")
        assert r.status_code == 200
        assert r.json()["deleted"] is True

    def test_mock_event_ingestion_text(self, client):
        event = json.loads((FIXTURES_DIR / "text_message.json").read_text())
        r = client.post("/integrations/telegram/mock-events",
                        json={"event": event, "owner_id": "user_123"})
        assert r.status_code == 200
        data = r.json()
        assert data["processed"] >= 1
        assert data["errors"] == 0

    def test_mock_event_disabled_chat_ignored(self, client):
        event = json.loads((FIXTURES_DIR / "disabled_chat_message.json").read_text())
        r = client.post("/integrations/telegram/mock-events",
                        json={"event": event, "owner_id": "user_123"})
        assert r.status_code == 200
        data = r.json()
        assert data["ignored"] >= 1

    def test_mock_event_batch(self, client):
        events = [
            json.loads((FIXTURES_DIR / "text_message.json").read_text()),
            json.loads((FIXTURES_DIR / "link_message.json").read_text()),
        ]
        r = client.post("/integrations/telegram/mock-events/batch",
                        json={"events": events, "owner_id": "user_123"})
        assert r.status_code == 200
        data = r.json()
        assert data["processed"] + data["ignored"] >= 2

    def test_pause_and_resume(self, client):
        r = client.post("/integrations/telegram/pause")
        assert r.status_code == 200
        assert r.json()["is_paused"] is True
        r = client.post("/integrations/telegram/resume")
        assert r.status_code == 200
        assert r.json()["is_paused"] is False

    def test_disconnect(self, client):
        r = client.post("/integrations/telegram/disconnect", json={"owner_id": "user_123"})
        assert r.status_code == 200
        assert r.json()["authorization_status"] == "disconnected"


# ===========================================================================
# 9. Regression tests — existing routes unaffected
# ===========================================================================

class TestRegressionExistingRoutes:
    """Confirm pre-existing routes still function after Telegram additions."""

    @pytest.fixture()
    def client(self, test_settings):
        from fastapi.testclient import TestClient
        from api.config import get_settings
        from api.main import create_app
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: test_settings
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c

    def test_health_endpoint_still_works(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert "version" in data

    def test_collections_endpoint_still_works(self, client):
        r = client.get("/collections")
        assert r.status_code == 200
        data = r.json()
        assert "collections" in data

    def test_query_endpoint_rejects_missing_collection(self, client):
        r = client.post("/query", json={
            "question": "test query",
            "collection_name": "nonexistent_collection_xyz_regression",
            "top_k": 3,
            "use_rag": False,
        })
        # Should return 404 (collection not found) — not 500
        assert r.status_code in (404, 422)

    def test_upload_endpoint_does_not_exist(self, client):
        """POST /upload must not exist in Telegram-only architecture."""
        from io import BytesIO
        r = client.post(
            "/upload",
            files={"file": ("test.txt", BytesIO(b"not a zip"), "text/plain")},
        )
        assert r.status_code == 404, "Upload endpoint must be removed in Telegram-only architecture"
