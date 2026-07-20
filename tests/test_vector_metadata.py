"""
tests/test_vector_metadata.py — Unit tests for VectorMetadata and
KnowledgeMetadataMapper (Tasks 2.3, 3.4, 6.5, 7.4, 8.6).
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from enum import Enum

from models.vector_metadata import VectorMetadata
from models.knowledge_object import KnowledgeObject
from app.integrations.telegram.mapping.knowledge_metadata_mapper import KnowledgeMetadataMapper
from app.retrieval.telegram_filter import (
    TelegramMetadataFilter,
    ChromaWhereBuilder,
    QueryScopeBuilder,
    EffectiveMetadataFilter,
    ConversationNotOwned,
    UnsupportedFilterCombination,
    InvalidTimestampFilter,
)
from exceptions.exceptions import MetadataFilterError


def _base_vm(**overrides) -> VectorMetadata:
    base = dict(owner_id="u1", source="telegram", content_type="text")
    base.update(overrides)
    return VectorMetadata(**base)


def _base_obj(**overrides) -> KnowledgeObject:
    base = dict(
        owner_id="owner_001", source="telegram",
        source_account_id="acc_001", conversation_id="conv_001",
        source_message_id="msg_001", sender_id="user_001",
        sender_name="Anu", content_type="text",
        text="Hello world",
        timestamp=datetime(2026, 7, 14, 10, 0, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return KnowledgeObject(**base)


# ===========================================================================
# VectorMetadata coercion (Task 2.3)
# ===========================================================================

class TestVectorMetadataCoercion:

    def test_datetime_coerced_to_iso_string(self):
        dt = datetime(2026, 7, 14, 10, 0, tzinfo=timezone.utc)
        vm = _base_vm(timestamp=dt)
        out = vm.to_vector_store_metadata()
        assert isinstance(out["timestamp"], str)
        assert "2026-07-14" in out["timestamp"]

    def test_none_timestamp_becomes_empty_string(self):
        vm = _base_vm(timestamp=None)
        out = vm.to_vector_store_metadata()
        assert out["timestamp"] == ""

    def test_enum_value_coerced_to_string(self):
        class FakeEnum(Enum):
            PRIVATE = "private"
        vm = _base_vm()
        from models.vector_metadata import VectorMetadata
        result = vm._coerce_enum_or_str(FakeEnum.PRIVATE)
        assert result == "private"

    def test_none_string_field_defaults_to_empty(self):
        vm = _base_vm(sender_id="", sender_name="")
        out = vm.to_vector_store_metadata()
        assert out["sender_id"] == ""
        assert out["sender_name"] == ""

    def test_bool_fields_preserved(self):
        vm = _base_vm(is_edited=True, is_deleted=False)
        out = vm.to_vector_store_metadata()
        assert out["is_edited"] is True
        assert out["is_deleted"] is False

    def test_int_chunk_index_preserved(self):
        vm = _base_vm(chunk_index=5)
        out = vm.to_vector_store_metadata()
        assert out["chunk_index"] == 5

    def test_extra_fields_merged_flat(self):
        vm = _base_vm(extra={"page_number": 3, "ocr_used": True})
        out = vm.to_vector_store_metadata()
        assert out["page_number"] == 3
        assert out["ocr_used"] is True

    def test_missing_owner_id_raises(self):
        vm = _base_vm(owner_id="")
        with pytest.raises(ValueError, match="owner_id"):
            vm.to_vector_store_metadata()

    def test_missing_source_raises(self):
        vm = _base_vm(source="")
        with pytest.raises(ValueError, match="source"):
            vm.to_vector_store_metadata()

    def test_all_values_are_scalar(self):
        vm = _base_vm(
            sender_id="s1", sender_name="Anu",
            conversation_id="c1", chunk_index=2,
            timestamp=datetime(2026, 7, 14, tzinfo=timezone.utc),
            is_edited=False,
        )
        out = vm.to_vector_store_metadata()
        for k, v in out.items():
            assert isinstance(v, (str, int, float, bool)), \
                f"Field {k!r} has non-scalar type {type(v).__name__}"

    def test_source_chat_fallback_to_conversation_id(self):
        vm = _base_vm(conversation_id="conv_xyz", conversation_title="", source_chat="")
        out = vm.to_vector_store_metadata()
        assert out["source_chat"] == "conv_xyz"


# ===========================================================================
# KnowledgeMetadataMapper (Task 3.4)
# ===========================================================================

class TestKnowledgeMetadataMapper:

    def _mapper(self):
        return KnowledgeMetadataMapper()

    def test_maps_required_fields(self):
        obj = _base_obj()
        vm = self._mapper().map(obj)
        assert vm.owner_id == "owner_001"
        assert vm.source == "telegram"
        assert vm.source_account_id == "acc_001"
        assert vm.conversation_id == "conv_001"
        assert vm.sender_id == "user_001"
        assert vm.sender_name == "Anu"
        assert vm.source_message_id == "msg_001"
        assert vm.content_type == "text"

    def test_timestamp_preserved_as_utc(self):
        obj = _base_obj()
        vm = self._mapper().map(obj)
        assert vm.timestamp is not None
        assert vm.timestamp.tzinfo is not None

    def test_chunk_index_and_content_part(self):
        obj = _base_obj()
        vm = self._mapper().map(obj, chunk_index=3, content_part="pdf")
        assert vm.chunk_index == 3

    def test_extra_scalar_fields_passed_through(self):
        obj = _base_obj()
        vm = self._mapper().map(obj, extra={"page_number": 7, "ocr_used": False})
        assert vm.extra["page_number"] == 7
        assert vm.extra["ocr_used"] is False

    def test_telegram_extras_from_metadata(self):
        obj = _base_obj(metadata={
            "conversation_title": "Anu Chat",
            "conversation_type": "private",
            "telegram_file_id": "file_abc",
        })
        vm = self._mapper().map(obj)
        assert vm.conversation_title == "Anu Chat"
        assert vm.conversation_type == "private"
        assert vm.attachment_id == "file_abc"

    def test_is_edited_and_deleted_propagated(self):
        obj = _base_obj(is_edited=True, is_deleted=False)
        vm = self._mapper().map(obj)
        assert vm.is_edited is True
        assert vm.is_deleted is False

    def test_vector_document_id_format(self):
        obj = _base_obj()
        vid = self._mapper().vector_document_id(obj, content_part="pdf", chunk_index=2)
        assert vid == "telegram:acc_001:conv_001:msg_001:pdf:2"

    def test_missing_owner_id_raises(self):
        obj = _base_obj(owner_id="")
        with pytest.raises(ValueError):
            self._mapper().map(obj)

    def test_mapping_pdf_content_type(self):
        obj = _base_obj(content_type="pdf", filename="doc.pdf", mime_type="application/pdf")
        vm = self._mapper().map(obj, content_part="pdf")
        assert vm.content_type == "pdf"
        assert vm.filename == "doc.pdf"
        assert vm.mime_type == "application/pdf"

    def test_mapping_voice_content_type(self):
        obj = _base_obj(content_type="voice")
        vm = self._mapper().map(obj, extra={"duration_seconds": 12, "transcript_segment": "hello"})
        assert vm.extra["duration_seconds"] == 12
        assert vm.extra["transcript_segment"] == "hello"

    def test_mapping_image_content_type(self):
        obj = _base_obj(content_type="image")
        vm = self._mapper().map(obj, extra={"ocr_used": True, "caption_present": True})
        assert vm.extra["ocr_used"] is True

    def test_non_scalar_extra_values_coerced(self):
        obj = _base_obj()
        vm = self._mapper().map(obj, extra={"slide_number": 5, "bad": [1, 2, 3]})
        out = vm.to_vector_store_metadata()
        assert out["slide_number"] == 5
        # [1,2,3] is coerced to string repr
        assert "bad" in out
        assert isinstance(out["bad"], str)


# ===========================================================================
# TelegramMetadataFilter validation (Task 6.5)
# ===========================================================================

class TestTelegramMetadataFilterValidation:

    def test_valid_filter_passes(self):
        f = TelegramMetadataFilter(source="telegram", conversation_id="c1")
        f.validate()

    def test_empty_string_owner_id_rejected(self):
        f = TelegramMetadataFilter(owner_id="")
        with pytest.raises(MetadataFilterError, match="owner_id"):
            f.validate()

    def test_empty_string_conversation_id_rejected(self):
        f = TelegramMetadataFilter(conversation_id="")
        with pytest.raises(MetadataFilterError, match="conversation_id"):
            f.validate()

    def test_singular_plural_conversation_conflict(self):
        f = TelegramMetadataFilter(conversation_id="c1", conversation_ids=["c1", "c2"])
        with pytest.raises(UnsupportedFilterCombination):
            f.validate()

    def test_singular_plural_content_type_conflict(self):
        f = TelegramMetadataFilter(content_type="text", content_types=["text", "pdf"])
        with pytest.raises(UnsupportedFilterCombination):
            f.validate()

    def test_unsupported_content_type_rejected(self):
        f = TelegramMetadataFilter(content_type="hologram")
        with pytest.raises(MetadataFilterError, match="content_type"):
            f.validate()

    def test_malformed_timestamp_from_rejected(self):
        f = TelegramMetadataFilter(timestamp_from="not-a-date")
        with pytest.raises(InvalidTimestampFilter):
            f.validate()

    def test_valid_timestamp_from_passes(self):
        f = TelegramMetadataFilter(timestamp_from="2026-07-13T18:00:00+05:30")
        f.validate()

    def test_conversation_ids_empty_string_rejected(self):
        f = TelegramMetadataFilter(conversation_ids=["c1", ""])
        with pytest.raises(MetadataFilterError, match="empty"):
            f.validate()


# ===========================================================================
# QueryScopeBuilder (Task 7.4)
# ===========================================================================

class TestQueryScopeBuilder:

    def test_owner_always_from_auth_context(self):
        scope = QueryScopeBuilder()
        f = TelegramMetadataFilter(owner_id="attacker_owner", source="telegram")
        f.validate()
        ef = scope.build("real_owner", f)
        assert ef.owner_id == "real_owner"

    def test_owner_id_none_in_filter_still_uses_auth(self):
        scope = QueryScopeBuilder()
        f = TelegramMetadataFilter(source="telegram")
        f.validate()
        ef = scope.build("auth_owner", f)
        assert ef.owner_id == "auth_owner"

    def test_conversation_rejected_by_custom_checker(self):
        class NeverOwned:
            def is_owned(self, o, c): return False
        scope = QueryScopeBuilder(NeverOwned())
        f = TelegramMetadataFilter(conversation_id="c1")
        f.validate()
        with pytest.raises(ConversationNotOwned):
            scope.build("u1", f)

    def test_multi_conversation_rejected_if_one_not_owned(self):
        class PartialOwner:
            def is_owned(self, o, c): return c != "c_forbidden"
        scope = QueryScopeBuilder(PartialOwner())
        f = TelegramMetadataFilter(conversation_ids=["c_ok", "c_forbidden"])
        f.validate()
        with pytest.raises(ConversationNotOwned):
            scope.build("u1", f)


# ===========================================================================
# ChromaWhereBuilder (Task 8.6)
# ===========================================================================

class TestChromaWhereBuilder:

    def _build(self, **kwargs) -> dict | None:
        ef = EffectiveMetadataFilter(owner_id=kwargs.pop("owner_id", "u1"), **kwargs)
        return ChromaWhereBuilder().build(ef)

    def test_owner_id_always_present(self):
        where = self._build()
        assert where is not None
        assert "owner_id" in str(where)

    def test_single_conversation_filter(self):
        where = self._build(source="telegram", conversation_id="c1")
        assert where is not None
        # Should be $and with owner, source, conversation_id
        assert "$and" in where
        conditions = where["$and"]
        fields = {list(c.keys())[0] for c in conditions}
        assert "owner_id" in fields
        assert "source" in fields
        assert "conversation_id" in fields

    def test_sender_id_added_for_group_query(self):
        where = self._build(source="telegram", conversation_id="g1", sender_id="s1")
        assert where is not None
        conds = where.get("$and", [])
        fields = {list(c.keys())[0] for c in conds}
        assert "sender_id" in fields

    def test_multi_conversation_uses_in_operator(self):
        where = self._build(source="telegram", conversation_ids=["c1", "c2"])
        assert where is not None
        conds_str = str(where)
        assert "$in" in conds_str

    def test_single_conversation_ids_list_uses_eq(self):
        where = self._build(conversation_ids=["c1"])
        conds_str = str(where)
        assert "$eq" in conds_str

    def test_content_type_filter(self):
        where = self._build(content_type="pdf")
        assert "content_type" in str(where)

    def test_content_types_multi_uses_in(self):
        where = self._build(content_types=["pdf", "docx"])
        assert "$in" in str(where)

    def test_no_filters_returns_just_owner(self):
        where = self._build()
        # Only owner_id condition — no $and needed (single condition)
        assert where == {"owner_id": {"$eq": "u1"}}

    def test_timestamp_from_adds_gte(self):
        from datetime import timezone
        ts = datetime(2026, 7, 1, tzinfo=timezone.utc)
        where = self._build(timestamp_from=ts)
        assert "$gte" in str(where)

    def test_timestamp_to_adds_lte(self):
        from datetime import timezone
        ts = datetime(2026, 7, 31, tzinfo=timezone.utc)
        where = self._build(timestamp_to=ts)
        assert "$lte" in str(where)
