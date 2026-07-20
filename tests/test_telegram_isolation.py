"""
tests/test_telegram_isolation.py — End-to-end isolation tests (Requirement 16).

These tests run against a REAL ChromaDB instance backed by tmp_path.
They insert actual vectors using fake embeddings, then query with
ChromaWhereBuilder-generated where-clauses and assert data never crosses
owner / conversation / sender boundaries.

All test data is synthetic — no real user messages.

Coverage (17.1–17.12):
  17.1  Private-chat isolation
  17.2  Cross-contact isolation (Anu vs Arun)
  17.3  Group-sender isolation
  17.4  Private-vs-group isolation
  17.5  Duplicate-display-name isolation (owner_1 Anu vs owner_2 Anu)
  17.6  Cross-owner isolation (spoofed owner_id attempt)
  17.7  Source-type isolation (Telegram vs non-Telegram)
  17.8  Content-type isolation
  17.9  Multi-conversation retrieval
  17.10 Unknown/unauthorized conversation handling
  17.11 Full metadata round-trip
  17.12 Stable vector ID dedup on reprocess
"""

from __future__ import annotations

import math
import pytest
from pathlib import Path
from typing import List

import chromadb

from models.knowledge_object import KnowledgeObject
from models.vector_metadata import VectorMetadata
from app.integrations.telegram.mapping.knowledge_metadata_mapper import KnowledgeMetadataMapper
from app.retrieval.telegram_filter import (
    ChromaWhereBuilder,
    EffectiveMetadataFilter,
    TelegramMetadataFilter,
    QueryScopeBuilder,
    ConversationNotOwned,
    UnsupportedFilterCombination,
    InvalidTimestampFilter,
)
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_DIM = 8

def _fake_vec(seed: int, dim: int = FAKE_DIM) -> List[float]:
    raw = [((seed * 7 + i * 13) % 17 - 8) / 8.0 for i in range(dim)]
    norm = math.sqrt(sum(v * v for v in raw)) or 1.0
    return [v / norm for v in raw]


def _make_obj(
    owner_id: str,
    account_id: str,
    chat_id: str,
    sender_id: str,
    sender_name: str,
    message_id: str,
    text: str,
    content_type: str = "text",
    source: str = "telegram",
    conv_title: str = "",
    conv_type: str = "private",
) -> KnowledgeObject:
    return KnowledgeObject(
        owner_id=owner_id,
        source=source,
        source_account_id=account_id,
        conversation_id=chat_id,
        source_message_id=message_id,
        sender_id=sender_id,
        sender_name=sender_name,
        content_type=content_type,
        text=text,
        timestamp=datetime(2026, 7, 14, 10, 0, tzinfo=timezone.utc),
        metadata={
            "conversation_title": conv_title or chat_id,
            "conversation_type": conv_type,
        },
    )


def _insert(col, obj: KnowledgeObject, seed: int, chunk_index: int = 0,
            content_part: str = "text") -> str:
    """Insert one KnowledgeObject into a ChromaDB collection. Returns vector_id."""
    mapper = KnowledgeMetadataMapper()
    vm = mapper.map(obj, chunk_index=chunk_index, content_part=content_part)
    meta = vm.to_vector_store_metadata()
    vid = mapper.vector_document_id(obj, content_part=content_part, chunk_index=chunk_index)
    col.add(
        ids=[vid],
        embeddings=[_fake_vec(seed)],
        documents=[obj.text or ""],
        metadatas=[meta],
    )
    return vid


def _query(col, seed: int, where: dict | None, top_k: int = 10) -> list[str]:
    """Query a collection by metadata filter (get-style), returning list of text values."""
    # Use col.get() for pure metadata filtering — isolation tests don't need
    # vector similarity ranking, they need exact metadata constraints.
    kwargs: dict = {"include": ["documents"]}
    if where:
        kwargs["where"] = where
    raw = col.get(**kwargs)
    return raw["documents"] if raw["documents"] else []


def _setup_isolation_collection(tmp_path: Path) -> chromadb.Collection:
    """
    Create a ChromaDB collection pre-populated with all isolation fixtures.
    Uses in-memory EphemeralClient to avoid PersistentClient path issues in pytest.
    """
    client = chromadb.EphemeralClient()
    col = client.get_or_create_collection("isolation_test", metadata={"hnsw:space": "cosine"})

    objects = [
        # owner_001 — Anu private
        (_make_obj("owner_001", "tg_account_owner1", "tg_private_anu_owner1",
                   "tg_user_anu_owner1", "Anu", "msg_001",
                   "The NEXORA project deadline is next Friday at 5 PM.",
                   conv_title="Anu", conv_type="private"), 1),
        # owner_001 — Anu group
        (_make_obj("owner_001", "tg_account_owner1", "tg_group_project_owner1",
                   "tg_user_anu_owner1", "Anu", "msg_002",
                   "Team, the API review meeting is scheduled for Monday morning.",
                   conv_title="Project Team", conv_type="group"), 2),
        # owner_001 — Arun group (same group as Anu)
        (_make_obj("owner_001", "tg_account_owner1", "tg_group_project_owner1",
                   "tg_user_arun_owner1", "Arun", "msg_003",
                   "The database migration is scheduled for Sunday at midnight.",
                   conv_title="Project Team", conv_type="group"), 3),
        # owner_001 — Arun private
        (_make_obj("owner_001", "tg_account_owner1", "tg_private_arun_owner1",
                   "tg_user_arun_owner1", "Arun", "msg_004",
                   "Running performance benchmarks on the new infrastructure.",
                   conv_title="Arun", conv_type="private"), 4),
        # owner_002 — Anu private (SAME display name "Anu", DIFFERENT sender_id)
        (_make_obj("owner_002", "tg_account_owner2", "tg_private_anu_owner2",
                   "tg_user_anu_owner2", "Anu", "msg_005",
                   "The cloud infrastructure budget was approved for Q3.",
                   conv_title="Anu", conv_type="private"), 5),
        # owner_002 — Arun private
        (_make_obj("owner_002", "tg_account_owner2", "tg_private_arun_owner2",
                   "tg_user_arun_owner2", "Arun", "msg_006",
                   "The security audit report will be ready by end of month.",
                   conv_title="Arun", conv_type="private"), 6),
        # Non-Telegram (source=whatsapp) — should never appear in Telegram queries
        (_make_obj("owner_001", "wa_account_001", "wa_chat_001",
                   "wa_user_001", "Alice", "wa_msg_001",
                   "WhatsApp legacy message about project timeline.",
                   source="whatsapp", conv_type="private"), 7),
        # PDF content_type
        (_make_obj("owner_001", "tg_account_owner1", "tg_private_anu_owner1",
                   "tg_user_anu_owner1", "Anu", "msg_007",
                   "PDF content: NEXORA technical specification document.",
                   content_type="pdf", conv_title="Anu", conv_type="private"), 8),
    ]

    for obj, seed in objects:
        ct = "pdf" if obj.content_type == "pdf" else "text"
        _insert(col, obj, seed, content_part=ct)

    return col


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestTelegramIsolation:
    """End-to-end isolation tests against real ChromaDB (tmp_path)."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.col = _setup_isolation_collection(tmp_path)
        self.builder = ChromaWhereBuilder()
        # Quick sanity check — at minimum 6 docs (without timing out)
        assert self.col.count() >= 6

    def _effective(self, owner_id: str, **kwargs) -> EffectiveMetadataFilter:
        return EffectiveMetadataFilter(owner_id=owner_id, **kwargs)

    def _docs(self, owner_id: str, **kwargs) -> list[str]:
        ef = self._effective(owner_id, **kwargs)
        where = self.builder.build(ef)
        return _query(self.col, 1, where)

    # 17.1 Private-chat isolation
    def test_17_1_private_chat_isolation(self):
        """Query owner_001 Anu private chat → only NEXORA/PDF docs, not group/Arun."""
        docs = self._docs(
            "owner_001", source="telegram",
            conversation_id="tg_private_anu_owner1"
        )
        assert any("NEXORA" in d or "specification" in d for d in docs), \
            "Should contain Anu's private message"
        assert not any("API review" in d for d in docs), \
            "Should NOT contain group message"
        assert not any("database migration" in d for d in docs), \
            "Should NOT contain Arun group message"

    # 17.2 Cross-contact isolation (Anu vs Arun)
    def test_17_2_cross_contact_isolation(self):
        """Query owner_001 Arun private → only Arun's message, not Anu's."""
        docs = self._docs(
            "owner_001", source="telegram",
            conversation_id="tg_private_arun_owner1"
        )
        assert any("performance benchmark" in d for d in docs), \
            "Should contain Arun's private message"
        assert not any("NEXORA" in d for d in docs), \
            "Should NOT contain Anu's private message"
        assert not any("infrastructure budget" in d for d in docs), \
            "Should NOT contain owner_002 data"

    # 17.3 Group-sender isolation (Anu in group only)
    def test_17_3_group_sender_isolation(self):
        """Query group + sender_id=Anu → only Anu's group message, not Arun's."""
        docs = self._docs(
            "owner_001", source="telegram",
            conversation_id="tg_group_project_owner1",
            sender_id="tg_user_anu_owner1",
        )
        assert any("API review" in d for d in docs), "Should contain Anu group message"
        assert not any("database migration" in d for d in docs), \
            "Should NOT contain Arun's group message"

    # 17.4 Private-vs-group isolation
    def test_17_4_private_vs_group_isolation(self):
        """Anu's private chat query must NOT return group messages."""
        docs = self._docs(
            "owner_001", source="telegram",
            conversation_id="tg_private_anu_owner1",
        )
        assert not any("API review" in d for d in docs), \
            "Private chat query must NOT leak group messages"

    # 17.5 Duplicate display name — owner_001 Anu vs owner_002 Anu
    def test_17_5_duplicate_display_name_isolation(self):
        """Two 'Anu' contacts with different sender_ids and owners must not mix."""
        # owner_002 Anu text: "The cloud infrastructure budget was approved for Q3."
        # owner_001 Anu text: "The NEXORA project deadline is next Friday at 5 PM."
        o1_docs = self._docs(
            "owner_001", source="telegram",
            conversation_id="tg_private_anu_owner1",
        )
        o2_docs = self._docs(
            "owner_002", source="telegram",
            conversation_id="tg_private_anu_owner2",
        )
        assert any("NEXORA" in d for d in o1_docs), "owner_001 should see their Anu"
        assert any("infrastructure budget" in d for d in o2_docs), \
            "owner_002 should see their Anu (text contains 'infrastructure budget')"
        assert not any("infrastructure budget" in d for d in o1_docs), \
            "owner_001 must NOT see owner_002's Anu data"
        assert not any("NEXORA" in d for d in o2_docs), \
            "owner_002 must NOT see owner_001's Anu data"

    # 17.6 Cross-owner isolation including spoofed owner_id
    def test_17_6_cross_owner_isolation_direct(self):
        """Direct owner_001 query must not return owner_002 data."""
        docs = self._docs("owner_001", source="telegram")
        assert not any("infrastructure budget" in d for d in docs), \
            "owner_001 must NOT see owner_002 cloud budget"
        assert not any("security audit" in d for d in docs), \
            "owner_001 must NOT see owner_002 security audit"

    def test_17_6_cross_owner_spoofed_rejected(self):
        """QueryScopeBuilder enforces authenticated owner over any client value."""
        scope = QueryScopeBuilder()
        # Client tries to send owner_id="owner_002" in filters
        tg_filter = TelegramMetadataFilter(owner_id="owner_002", source="telegram")
        tg_filter.validate()
        # But authenticated_owner_id="owner_001" overrides it
        effective = scope.build(
            authenticated_owner_id="owner_001",
            requested_filters=tg_filter,
        )
        assert effective.owner_id == "owner_001", \
            "Authenticated owner must override client-supplied owner_id"
        where = self.builder.build(effective)
        docs = _query(self.col, 1, where)
        assert not any("infrastructure budget" in d for d in docs), \
            "Spoofed owner_id must not allow cross-owner access"

    # 17.7 Source-type isolation (Telegram vs non-Telegram)
    def test_17_7_source_type_isolation(self):
        """Telegram query must not return WhatsApp legacy documents."""
        docs = self._docs("owner_001", source="telegram")
        assert not any("WhatsApp legacy" in d for d in docs), \
            "Telegram filter must exclude WhatsApp source"

    def test_17_7_no_source_filter_includes_telegram(self):
        """Without source filter, owner_001 still gets Telegram docs."""
        docs = self._docs("owner_001")
        assert any("NEXORA" in d or "API review" in d or "benchmark" in d for d in docs)

    # 17.8 Content-type isolation
    def test_17_8_content_type_isolation(self):
        """Filtering content_type=pdf must return only PDF chunks."""
        docs = self._docs("owner_001", source="telegram", content_type="pdf")
        assert any("specification" in d for d in docs), "PDF chunk should be returned"
        assert not any("API review" in d for d in docs), \
            "Text-type messages must not appear in pdf filter"

    # 17.9 Multi-conversation retrieval
    def test_17_9_multi_conversation_retrieval(self):
        """conversation_ids=[private_anu, private_arun] returns both, not group."""
        docs = self._docs(
            "owner_001", source="telegram",
            conversation_ids=["tg_private_anu_owner1", "tg_private_arun_owner1"],
        )
        assert any("NEXORA" in d or "specification" in d for d in docs), \
            "Should include Anu private"
        assert any("performance benchmark" in d for d in docs), \
            "Should include Arun private"
        assert not any("API review" in d for d in docs), \
            "Group messages must not appear"

    # 17.10 Unknown/unauthorized conversation handling
    def test_17_10_unknown_conversation_returns_empty(self):
        """Filtering on a non-existent conversation_id returns no results."""
        docs = self._docs(
            "owner_001", source="telegram",
            conversation_id="tg_nonexistent_chat_xyz",
        )
        assert len(docs) == 0, "Unknown conversation must return no results"

    def test_17_10_ownership_checker_rejects_unknown(self):
        """ConversationNotOwned raised when ownership checker rejects conversation."""
        class _RejectAll:
            def is_owned(self, owner_id, conv_id): return False

        scope = QueryScopeBuilder(ownership_checker=_RejectAll())
        tg_filter = TelegramMetadataFilter(
            source="telegram", conversation_id="tg_chat_not_mine"
        )
        tg_filter.validate()
        with pytest.raises(ConversationNotOwned):
            scope.build("owner_001", tg_filter)

    # 17.11 Full metadata round-trip
    def test_17_11_full_metadata_round_trip(self):
        """KnowledgeObject → VectorMetadata → ChromaDB → query result metadata intact."""
        # Fetch metadata from the collection for msg_001
        result = self.col.get(
            where={"$and": [
                {"owner_id": {"$eq": "owner_001"}},
                {"source_message_id": {"$eq": "msg_001"}},
            ]},
            include=["metadatas", "documents"],
        )
        assert result["ids"], "msg_001 must be in the collection"
        meta = result["metadatas"][0]
        assert meta["owner_id"] == "owner_001"
        assert meta["source"] == "telegram"
        assert meta["source_account_id"] == "tg_account_owner1"
        assert meta["conversation_id"] == "tg_private_anu_owner1"
        assert meta["sender_id"] == "tg_user_anu_owner1"
        assert meta["sender_name"] == "Anu"
        assert meta["source_message_id"] == "msg_001"
        assert meta["content_type"] == "text"
        assert "NEXORA" in result["documents"][0]

    # 17.12 Stable vector ID dedup on reprocess
    def test_17_12_stable_vector_id_dedup(self, tmp_path):
        """Processing the same KnowledgeObject twice must produce exactly 1 vector."""
        client = chromadb.EphemeralClient()
        col = client.get_or_create_collection("dedup_col", metadata={"hnsw:space": "cosine"})

        obj = _make_obj("owner_001", "tg_account_owner1", "tg_private_anu_owner1",
                        "tg_user_anu_owner1", "Anu", "msg_dedup_001",
                        "Dedup test message about NEXORA.")

        vid1 = _insert(col, obj, seed=99)
        count_after_first = col.count()

        vid2 = _insert(col, obj, seed=99)  # same vector ID → overwrites
        count_after_second = col.count()

        assert vid1 == vid2, "Same message must produce same vector ID"
        assert count_after_first == count_after_second, \
            "Re-inserting same ID must not create duplicate (ChromaDB upsert)"
        assert count_after_first == 1
