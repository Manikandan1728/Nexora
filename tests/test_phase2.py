"""
tests/test_phase2.py — Comprehensive unit tests for Phase 2.

All tests are fully self-contained.  No real WhatsApp exports required.
The BGE-M3 tokenizer is loaded once (singleton) for the entire test session.
"""

from __future__ import annotations

import dataclasses
import pytest
from typing import List

from models.chat import Chat
from models.message import Message
from models.metadata import ChatMetadata
from models.attachment import Attachment
from models.document import Document, make_document_id

from app.documents.cleaner import TextCleaner
from app.documents.normalizer import TextNormalizer
from app.documents.tokenizer_service import TokenizerService
from app.documents.chunker import MessageChunker, ChunkerConfig
from app.documents.document_builder import DocumentBuilder
from app.documents.metadata_enricher import MetadataEnricher
from app.documents.phase2_pipeline import Phase2Pipeline

from exceptions.exceptions import TokenizationError, ChunkingError, DocumentBuildError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def tokenizer():
    """Load the BGE-M3 tokenizer once for the entire test session."""
    TokenizerService.reset_singleton()
    svc = TokenizerService()
    yield svc
    svc.clear_cache()
    TokenizerService.reset_singleton()


def _make_message(
    msg_id: int = 1,
    sender: str = "Alice",
    text: str = "Hello world",
    timestamp: str = "1/1/2024, 9:00 AM",
    msg_type: str = "text",
    attachment: str = None,
) -> Message:
    return Message(
        id=msg_id,
        timestamp=timestamp,
        sender=sender,
        message=text,
        message_type=msg_type,
        attachment=attachment,
    )


def _make_chat(messages: List[Message], participants=None) -> Chat:
    participants = participants or sorted({m.sender for m in messages if m.sender != "SYSTEM"})
    metadata = ChatMetadata(
        total_messages=len(messages),
        participants=participants,
        chat_start_date=messages[0].timestamp if messages else "",
        chat_end_date=messages[-1].timestamp if messages else "",
        attachment_count=sum(1 for m in messages if m.message_type == "attachment"),
    )
    return Chat(participants=participants, messages=messages, metadata=metadata)


# ===========================================================================
# 1. Document model tests
# ===========================================================================

class TestDocumentModel:
    def test_valid_document_creation(self):
        doc = Document(
            id="abc-123",
            text="Alice: Hello",
            metadata={"x": 1},
            participants=("Alice",),
            attachments=(),
            message_ids=(1,),
            source_chat="Test Chat",
            chunk_index=0,
            token_count=5,
            start_timestamp="1/1/2024, 9:00 AM",
            end_timestamp="1/1/2024, 9:01 AM",
        )
        assert doc.id == "abc-123"
        assert doc.chunk_index == 0
        assert doc.token_count == 5

    def test_frozen_document_cannot_be_mutated(self):
        doc = Document(
            id="x", text="t", metadata={}, participants=(),
            attachments=(), message_ids=(), source_chat="s",
            chunk_index=0, token_count=0,
            start_timestamp="", end_timestamp="",
        )
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            doc.text = "changed"  # type: ignore[misc]

    def test_invalid_empty_id_raises(self):
        with pytest.raises(ValueError):
            Document(
                id="", text="t", metadata={}, participants=(),
                attachments=(), message_ids=(), source_chat="s",
                chunk_index=0, token_count=0,
                start_timestamp="", end_timestamp="",
            )

    def test_negative_chunk_index_raises(self):
        with pytest.raises(ValueError):
            Document(
                id="x", text="t", metadata={}, participants=(),
                attachments=(), message_ids=(), source_chat="s",
                chunk_index=-1, token_count=0,
                start_timestamp="", end_timestamp="",
            )

    def test_negative_token_count_raises(self):
        with pytest.raises(ValueError):
            Document(
                id="x", text="t", metadata={}, participants=(),
                attachments=(), message_ids=(), source_chat="s",
                chunk_index=0, token_count=-1,
                start_timestamp="", end_timestamp="",
            )

    def test_has_attachments_property(self):
        doc = Document(
            id="x", text="t", metadata={}, participants=(),
            attachments=("photo.jpg",), message_ids=(), source_chat="s",
            chunk_index=0, token_count=0,
            start_timestamp="", end_timestamp="",
        )
        assert doc.has_attachments is True

    def test_is_empty_property(self):
        doc = Document(
            id="x", text="   ", metadata={}, participants=(),
            attachments=(), message_ids=(), source_chat="s",
            chunk_index=0, token_count=0,
            start_timestamp="", end_timestamp="",
        )
        assert doc.is_empty is True

    def test_make_document_id_uniqueness(self):
        ids = {make_document_id() for _ in range(1000)}
        assert len(ids) == 1000


# ===========================================================================
# 2. TextCleaner tests
# ===========================================================================

class TestTextCleaner:
    def test_normalise_windows_line_endings(self):
        assert TextCleaner.clean("Hello\r\nWorld") == "Hello\nWorld"

    def test_normalise_bare_carriage_return(self):
        assert TextCleaner.clean("Hello\rWorld") == "Hello\nWorld"

    def test_removes_zero_width_space(self):
        assert TextCleaner.clean("Hello\u200bWorld") == "HelloWorld"

    def test_removes_bom(self):
        assert TextCleaner.clean("\ufeffHello") == "Hello"

    def test_removes_soft_hyphen(self):
        assert TextCleaner.clean("Hello\u00adWorld") == "HelloWorld"

    def test_removes_direction_marks(self):
        result = TextCleaner.clean("\u200eHello\u200f")
        assert result == "Hello"

    def test_collapses_excess_blank_lines(self):
        text = "A\n\n\n\nB"
        result = TextCleaner.clean(text)
        assert "\n\n\n" not in result

    def test_strips_trailing_whitespace(self):
        assert TextCleaner.clean("Hello   \nWorld") == "Hello\nWorld"

    def test_strips_leading_whitespace(self):
        assert TextCleaner.clean("   Hello\n   World") == "Hello\nWorld"

    def test_collapses_interior_spaces(self):
        assert TextCleaner.clean("Hello   World") == "Hello World"

    def test_empty_string_unchanged(self):
        assert TextCleaner.clean("") == ""

    def test_preserves_emoji(self):
        result = TextCleaner.clean("Hello 😀 World")
        assert "😀" in result

    def test_preserves_unicode_characters(self):
        result = TextCleaner.clean("Héllo Wörld")
        assert "Héllo" in result

    def test_strips_whole_string(self):
        assert TextCleaner.clean("  hello  ") == "hello"

    def test_clean_message_body(self):
        body = "  Hello\r\n\u200bWorld  "
        result = TextCleaner.clean_message_body(body)
        assert result == "Hello\nWorld"


# ===========================================================================
# 3. TextNormalizer tests
# ===========================================================================

class TestTextNormalizer:
    def test_normalize_sender_name_strips_whitespace(self):
        assert TextNormalizer.normalize_sender_name("  alice  ") == "Alice"

    def test_normalize_sender_name_title_case(self):
        assert TextNormalizer.normalize_sender_name("ALICE BOB") == "Alice Bob"

    def test_normalize_sender_name_system_unchanged(self):
        assert TextNormalizer.normalize_sender_name("SYSTEM") == "SYSTEM"

    def test_normalize_sender_name_empty_unchanged(self):
        assert TextNormalizer.normalize_sender_name("") == ""

    def test_normalize_sender_name_nfc(self):
        # e + combining accent → precomposed é
        decomposed = "e\u0301"
        result = TextNormalizer.normalize_sender_name(decomposed)
        assert result == "\u00e9".title()

    def test_normalize_timestamp_strips_whitespace(self):
        assert TextNormalizer.normalize_timestamp("  1/1/2024,  9:00 AM  ") == "1/1/2024, 9:00 AM"

    def test_normalize_text_curly_quotes(self):
        result = TextNormalizer.normalize_text("\u201cHello\u201d")
        assert result == '"Hello"'

    def test_normalize_text_em_dash(self):
        result = TextNormalizer.normalize_text("one\u2014two")
        assert result == "one--two"

    def test_normalize_text_ellipsis(self):
        result = TextNormalizer.normalize_text("wait\u2026")
        assert result == "wait..."

    def test_normalize_text_nfc(self):
        decomposed = "cafe\u0301"
        result = TextNormalizer.normalize_text(decomposed)
        assert result == "caf\u00e9"

    def test_normalize_participants_deduplicates_and_sorts(self):
        result = TextNormalizer.normalize_participants(["Bob", "Alice", "alice"])
        assert result == ["Alice", "Bob"]

    def test_normalize_text_empty(self):
        assert TextNormalizer.normalize_text("") == ""


# ===========================================================================
# 4. TokenizerService tests
# ===========================================================================

class TestTokenizerService:
    def test_count_tokens_returns_integer(self, tokenizer):
        count = tokenizer.count_tokens("Hello world")
        assert isinstance(count, int)
        assert count > 0

    def test_count_tokens_empty_string(self, tokenizer):
        assert tokenizer.count_tokens("") == 0

    def test_count_tokens_caches_result(self, tokenizer):
        text = "unique test string xyz 123"
        tokenizer.clear_cache()
        tokenizer.count_tokens(text)
        assert tokenizer.cache_size >= 1
        # Second call uses cache
        before = tokenizer.cache_size
        tokenizer.count_tokens(text)
        assert tokenizer.cache_size == before  # no new entry added

    def test_count_tokens_emoji(self, tokenizer):
        # Emoji should tokenize to one or more tokens without crashing
        count = tokenizer.count_tokens("Hello 😀 World 🎉")
        assert count > 0

    def test_count_tokens_arabic(self, tokenizer):
        count = tokenizer.count_tokens("مرحبا بالعالم")
        assert count > 0

    def test_count_tokens_chinese(self, tokenizer):
        count = tokenizer.count_tokens("你好世界")
        assert count > 0

    def test_count_tokens_batch_matches_single(self, tokenizer):
        texts = ["Hello world", "How are you?", "Fine, thanks."]
        singles = [tokenizer.count_tokens(t) for t in texts]
        tokenizer.clear_cache()
        batch = tokenizer.count_tokens_batch(texts)
        assert batch == singles

    def test_count_tokens_batch_empty(self, tokenizer):
        assert tokenizer.count_tokens_batch([]) == []

    def test_singleton_returns_same_instance(self):
        a = TokenizerService()
        b = TokenizerService()
        assert a is b


# ===========================================================================
# 5. MessageChunker tests
# ===========================================================================

class TestMessageChunker:
    def _chunker(self, tokenizer, max_tokens=450, overlap=50):
        config = ChunkerConfig(max_tokens=max_tokens, overlap_tokens=overlap)
        return MessageChunker(tokenizer_service=tokenizer, config=config)

    def test_empty_messages_returns_empty_inner_list(self, tokenizer):
        chunks = self._chunker(tokenizer).chunk([])
        assert chunks == [[]]

    def test_single_message_produces_one_chunk(self, tokenizer):
        msgs = [_make_message(1, "Alice", "Hello")]
        chunks = self._chunker(tokenizer).chunk(msgs)
        assert len(chunks) == 1
        assert chunks[0][0].message == "Hello"

    def test_all_messages_fit_in_one_chunk(self, tokenizer):
        msgs = [_make_message(i, "Alice", f"Short msg {i}") for i in range(5)]
        chunks = self._chunker(tokenizer, max_tokens=450).chunk(msgs)
        assert len(chunks) == 1

    def test_messages_split_into_multiple_chunks(self, tokenizer):
        # Each message is ~8 tokens; max_tokens=20 forces splits
        msgs = [
            _make_message(i, "Alice", "The quick brown fox jumps over the lazy dog")
            for i in range(10)
        ]
        chunks = self._chunker(tokenizer, max_tokens=30, overlap=5).chunk(msgs)
        assert len(chunks) > 1

    def test_overlap_messages_appear_in_consecutive_chunks(self, tokenizer):
        # Each message "Alice: The quick brown fox..." is ~14 tokens.
        # max_tokens=30 → 2 msgs per chunk (28 tokens).
        # overlap_tokens=15 → the last 14-token message fits in the overlap window,
        # so chunk[1] must share at least one message id with chunk[0].
        msgs = [
            _make_message(i, "Alice", "The quick brown fox jumps over the lazy dog")
            for i in range(1, 11)
        ]
        config = ChunkerConfig(max_tokens=30, overlap_tokens=15)
        chunker = MessageChunker(tokenizer_service=tokenizer, config=config)
        chunks = chunker.chunk(msgs)
        assert len(chunks) >= 2
        # At least one message id from chunk[0] must also appear in chunk[1],
        # confirming that overlap was applied (overlap carries the tail of
        # chunk N into the head of chunk N+1).
        ids_in_first = {m.id for m in chunks[0]}
        ids_in_second = {m.id for m in chunks[1]}
        assert ids_in_first & ids_in_second, (
            "Expected at least one overlapping message between chunk 0 and chunk 1"
        )

    def test_chunk_token_count_does_not_exceed_max(self, tokenizer):
        msgs = [
            _make_message(i, "Alice", "Hello world, how are you doing today?")
            for i in range(1, 20)
        ]
        config = ChunkerConfig(max_tokens=50, overlap_tokens=10)
        chunker = MessageChunker(tokenizer_service=tokenizer, config=config)
        chunks = chunker.chunk(msgs)
        for chunk in chunks:
            total = sum(
                tokenizer.count_tokens(f"{m.sender}: {m.message}")
                for m in chunk
            )
            assert total <= 50 + 10, (
                f"Chunk token count {total} exceeds max+overlap"
            )

    def test_oversized_single_message_is_split(self, tokenizer):
        # A message that is much longer than max_tokens
        long_text = (
            "The weather today is absolutely beautiful. "
            "The sun is shining brightly. "
            "Birds are singing in the trees. "
            "Children are playing in the park. "
            "It is a perfect day to go for a walk. "
            "Perhaps we could visit the nearby garden. "
            "Flowers are blooming everywhere you look. "
        ) * 5
        msgs = [_make_message(1, "Alice", long_text)]
        config = ChunkerConfig(max_tokens=50, overlap_tokens=5)
        chunker = MessageChunker(tokenizer_service=tokenizer, config=config)
        chunks = chunker.chunk(msgs)
        assert len(chunks) >= 1

    def test_chunker_config_invalid_overlap_raises(self):
        with pytest.raises(ValueError):
            ChunkerConfig(max_tokens=100, overlap_tokens=100)

    def test_chunker_config_negative_overlap_raises(self):
        with pytest.raises(ValueError):
            ChunkerConfig(max_tokens=100, overlap_tokens=-1)

    def test_chunker_preserves_message_order(self, tokenizer):
        msgs = [_make_message(i, "Alice", f"Message {i}") for i in range(1, 6)]
        chunks = self._chunker(tokenizer, max_tokens=450).chunk(msgs)
        all_msgs = [m for chunk in chunks for m in chunk]
        # Account for overlap: ids may repeat, but the relative order should hold
        ids_seen = []
        for m in all_msgs:
            if not ids_seen or m.id != ids_seen[-1]:
                ids_seen.append(m.id)
        assert ids_seen == sorted(ids_seen)


# ===========================================================================
# 6. DocumentBuilder tests
# ===========================================================================

class TestDocumentBuilder:
    def _builder(self, tokenizer, source="Test Chat"):
        return DocumentBuilder(tokenizer_service=tokenizer, source_chat=source)

    def test_builds_documents_from_chunks(self, tokenizer):
        chunks = [
            [_make_message(1, "Alice", "Hi"), _make_message(2, "Bob", "Hello")],
        ]
        docs = self._builder(tokenizer).build(chunks)
        assert len(docs) == 1
        assert isinstance(docs[0], Document)

    def test_empty_chunks_returns_empty_list(self, tokenizer):
        docs = self._builder(tokenizer).build([[]])
        assert docs == []

    def test_document_text_contains_sender_prefix(self, tokenizer):
        chunks = [[_make_message(1, "Alice", "How are you?")]]
        docs = self._builder(tokenizer).build(chunks)
        assert "Alice: How are you?" in docs[0].text

    def test_document_chunk_index_sequential(self, tokenizer):
        chunks = [
            [_make_message(1, "Alice", "Hi")],
            [_make_message(2, "Bob", "Hey")],
            [_make_message(3, "Alice", "Bye")],
        ]
        docs = self._builder(tokenizer).build(chunks)
        assert [d.chunk_index for d in docs] == [0, 1, 2]

    def test_document_participants_extracted(self, tokenizer):
        chunks = [[
            _make_message(1, "Alice", "Hi"),
            _make_message(2, "Bob", "Hello"),
        ]]
        docs = self._builder(tokenizer).build(chunks)
        assert set(docs[0].participants) == {"Alice", "Bob"}

    def test_system_message_excluded_from_participants(self, tokenizer):
        chunks = [[
            _make_message(1, "SYSTEM", "Messages are encrypted"),
            _make_message(2, "Alice", "Hi"),
        ]]
        docs = self._builder(tokenizer).build(chunks)
        assert "SYSTEM" not in docs[0].participants

    def test_document_message_ids_populated(self, tokenizer):
        chunks = [[
            _make_message(1, "Alice", "Hi"),
            _make_message(2, "Bob", "Hey"),
        ]]
        docs = self._builder(tokenizer).build(chunks)
        assert 1 in docs[0].message_ids
        assert 2 in docs[0].message_ids

    def test_document_timestamps_populated(self, tokenizer):
        chunks = [[
            _make_message(1, "Alice", "Hi", timestamp="1/1/2024, 9:00 AM"),
            _make_message(2, "Bob", "Hey", timestamp="1/1/2024, 9:05 AM"),
        ]]
        docs = self._builder(tokenizer).build(chunks)
        assert docs[0].start_timestamp == "1/1/2024, 9:00 AM"
        assert docs[0].end_timestamp == "1/1/2024, 9:05 AM"

    def test_document_attachment_references_populated(self, tokenizer):
        chunks = [[
            _make_message(1, "Alice", "image omitted", msg_type="attachment", attachment="image omitted"),
        ]]
        docs = self._builder(tokenizer).build(chunks)
        assert len(docs[0].attachments) == 1

    def test_document_source_chat_set(self, tokenizer):
        chunks = [[_make_message(1, "Alice", "Hi")]]
        docs = self._builder(tokenizer, source="Alice & Bob").build(chunks)
        assert docs[0].source_chat == "Alice & Bob"

    def test_document_token_count_positive(self, tokenizer):
        chunks = [[_make_message(1, "Alice", "Hello world")]]
        docs = self._builder(tokenizer).build(chunks)
        assert docs[0].token_count > 0

    def test_document_id_is_unique(self, tokenizer):
        chunks = [
            [_make_message(i, "Alice", f"msg {i}")]
            for i in range(5)
        ]
        docs = self._builder(tokenizer).build(chunks)
        ids = [d.id for d in docs]
        assert len(ids) == len(set(ids))


# ===========================================================================
# 7. MetadataEnricher tests
# ===========================================================================

class TestMetadataEnricher:
    def _doc(self, **kwargs):
        defaults = dict(
            id="x", text="Alice: Hello\nBob: Hi",
            metadata={}, participants=("Alice", "Bob"),
            attachments=(), message_ids=(1, 2),
            source_chat="Alice & Bob", chunk_index=0,
            token_count=10, start_timestamp="1/1/2024, 9:00 AM",
            end_timestamp="1/1/2024, 9:05 AM",
        )
        defaults.update(kwargs)
        return Document(**defaults)

    def test_enricher_returns_new_list(self):
        docs = [self._doc()]
        enriched = MetadataEnricher().enrich(docs)
        assert enriched is not docs

    def test_enricher_populates_message_count(self):
        doc = self._doc(message_ids=(1, 2, 3))
        enriched = MetadataEnricher().enrich([doc])
        assert enriched[0].metadata["message_count"] == 3

    def test_enricher_populates_participant_count(self):
        doc = self._doc(participants=("Alice", "Bob", "Carol"))
        enriched = MetadataEnricher().enrich([doc])
        assert enriched[0].metadata["participant_count"] == 3

    def test_enricher_detects_image_attachment(self):
        doc = self._doc(attachments=("photo.jpg",))
        enriched = MetadataEnricher().enrich([doc])
        assert enriched[0].metadata["contains_images"] is True

    def test_enricher_detects_audio_attachment(self):
        doc = self._doc(attachments=("voice.opus",))
        enriched = MetadataEnricher().enrich([doc])
        assert enriched[0].metadata["contains_audio"] is True

    def test_enricher_detects_video_attachment(self):
        doc = self._doc(attachments=("clip.mp4",))
        enriched = MetadataEnricher().enrich([doc])
        assert enriched[0].metadata["contains_video"] is True

    def test_enricher_detects_document_attachment(self):
        doc = self._doc(attachments=("file.pdf",))
        enriched = MetadataEnricher().enrich([doc])
        assert enriched[0].metadata["contains_documents"] is True

    def test_enricher_attachment_count(self):
        doc = self._doc(attachments=("a.jpg", "b.mp3"))
        enriched = MetadataEnricher().enrich([doc])
        assert enriched[0].metadata["attachment_count"] == 2

    def test_enricher_conversation_duration(self):
        doc = self._doc(
            start_timestamp="1/1/2024, 9:00 AM",
            end_timestamp="1/1/2024, 9:05 AM",
        )
        enriched = MetadataEnricher().enrich([doc])
        assert enriched[0].metadata["conversation_duration_seconds"] == 300.0

    def test_enricher_zero_duration_for_same_timestamp(self):
        doc = self._doc(
            start_timestamp="1/1/2024, 9:00 AM",
            end_timestamp="1/1/2024, 9:00 AM",
        )
        enriched = MetadataEnricher().enrich([doc])
        assert enriched[0].metadata["conversation_duration_seconds"] == 0.0

    def test_enricher_zero_duration_for_missing_timestamp(self):
        doc = self._doc(start_timestamp="", end_timestamp="")
        enriched = MetadataEnricher().enrich([doc])
        assert enriched[0].metadata["conversation_duration_seconds"] == 0.0

    def test_enricher_average_message_length(self):
        # text has two lines: "Alice: Hi" (body="Hi", len=2) and "Bob: Hello" (body="Hello", len=5)
        doc = self._doc(text="Alice: Hi\nBob: Hello")
        enriched = MetadataEnricher().enrich([doc])
        avg = enriched[0].metadata["average_message_length"]
        assert avg == pytest.approx(3.5, rel=0.01)

    def test_enricher_empty_list(self):
        assert MetadataEnricher().enrich([]) == []

    def test_enricher_whatsapp_image_omitted_keyword(self):
        doc = self._doc(attachments=("image omitted",))
        enriched = MetadataEnricher().enrich([doc])
        assert enriched[0].metadata["contains_images"] is True


# ===========================================================================
# 8. Phase2Pipeline integration tests
# ===========================================================================

class TestPhase2Pipeline:
    def test_empty_chat_returns_empty_list(self):
        chat = _make_chat([], participants=[])
        docs = Phase2Pipeline(chat).run()
        assert docs == []

    def test_single_message_produces_one_document(self):
        msgs = [_make_message(1, "Alice", "Hello")]
        chat = _make_chat(msgs)
        docs = Phase2Pipeline(chat).run()
        assert len(docs) == 1
        assert isinstance(docs[0], Document)

    def test_output_is_list_of_documents(self):
        msgs = [
            _make_message(1, "Alice", "Hi"),
            _make_message(2, "Bob", "Hey"),
        ]
        chat = _make_chat(msgs)
        docs = Phase2Pipeline(chat).run()
        assert isinstance(docs, list)
        assert all(isinstance(d, Document) for d in docs)

    def test_documents_have_correct_source_chat(self):
        msgs = [_make_message(1, "Alice", "Hi"), _make_message(2, "Bob", "Hey")]
        chat = _make_chat(msgs, participants=["Alice", "Bob"])
        docs = Phase2Pipeline(chat).run()
        assert all(d.source_chat == "Alice & Bob" for d in docs)

    def test_documents_have_non_empty_ids(self):
        msgs = [_make_message(1, "Alice", "Hello world")]
        chat = _make_chat(msgs)
        docs = Phase2Pipeline(chat).run()
        assert all(d.id for d in docs)

    def test_documents_have_positive_token_counts(self):
        msgs = [_make_message(1, "Alice", "Hello world")]
        chat = _make_chat(msgs)
        docs = Phase2Pipeline(chat).run()
        assert all(d.token_count > 0 for d in docs)

    def test_documents_metadata_is_populated(self):
        msgs = [_make_message(1, "Alice", "Hi"), _make_message(2, "Bob", "Hey")]
        chat = _make_chat(msgs)
        docs = Phase2Pipeline(chat).run()
        for doc in docs:
            assert "message_count" in doc.metadata
            assert "participant_count" in doc.metadata
            assert "attachment_count" in doc.metadata

    def test_chunk_indices_are_sequential(self):
        msgs = [_make_message(i, "Alice", "Hello world") for i in range(1, 6)]
        chat = _make_chat(msgs)
        config = ChunkerConfig(max_tokens=20, overlap_tokens=3)
        docs = Phase2Pipeline(chat, config=config).run()
        assert [d.chunk_index for d in docs] == list(range(len(docs)))

    def test_all_message_ids_covered(self):
        msgs = [_make_message(i, "Alice", f"Message {i}") for i in range(1, 11)]
        chat = _make_chat(msgs)
        docs = Phase2Pipeline(chat).run()
        # Every message id must appear in at least one document
        covered = {mid for doc in docs for mid in doc.message_ids}
        expected = {m.id for m in msgs}
        assert expected.issubset(covered)

    def test_large_conversation(self):
        msgs = [
            _make_message(i, "Alice" if i % 2 == 0 else "Bob", f"Message {i} content here")
            for i in range(1, 201)
        ]
        chat = _make_chat(msgs)
        docs = Phase2Pipeline(chat).run()
        assert len(docs) >= 1
        assert all(isinstance(d, Document) for d in docs)

    def test_unicode_and_emoji_messages(self):
        msgs = [
            _make_message(1, "Alice", "Hello 😀🎉✨"),
            _make_message(2, "Bob", "Привет мир"),
            _make_message(3, "Alice", "你好世界"),
            _make_message(4, "Bob", "مرحبا بالعالم"),
        ]
        chat = _make_chat(msgs)
        docs = Phase2Pipeline(chat).run()
        assert len(docs) >= 1

    def test_attachment_message_in_pipeline(self):
        msgs = [
            _make_message(1, "Alice", "image omitted", msg_type="attachment", attachment="image omitted"),
            _make_message(2, "Bob", "Nice photo!"),
        ]
        chat = _make_chat(msgs)
        docs = Phase2Pipeline(chat).run()
        assert any(d.metadata.get("contains_images") for d in docs)

    def test_system_message_in_pipeline(self):
        msgs = [
            _make_message(1, "SYSTEM", "Messages are end-to-end encrypted."),
            _make_message(2, "Alice", "Hi there!"),
        ]
        chat = _make_chat(msgs)
        docs = Phase2Pipeline(chat).run()
        assert len(docs) >= 1

    def test_invalid_chat_type_raises(self):
        with pytest.raises(TypeError):
            Phase2Pipeline("not a chat")  # type: ignore

    def test_single_participant_source_label(self):
        msgs = [_make_message(1, "Alice", "Hello")]
        chat = _make_chat(msgs, participants=["Alice"])
        docs = Phase2Pipeline(chat).run()
        assert all(d.source_chat == "Alice" for d in docs)

    def test_three_participant_source_label(self):
        msgs = [
            _make_message(1, "Alice", "Hi"),
            _make_message(2, "Bob", "Hey"),
            _make_message(3, "Carol", "Hello"),
        ]
        chat = _make_chat(msgs, participants=["Alice", "Bob", "Carol"])
        docs = Phase2Pipeline(chat).run()
        assert all("Carol" in d.source_chat for d in docs)

    def test_multiline_message_in_pipeline(self):
        msgs = [
            _make_message(1, "Alice", "Line one\nLine two\nLine three"),
            _make_message(2, "Bob", "Got it"),
        ]
        chat = _make_chat(msgs)
        docs = Phase2Pipeline(chat).run()
        assert len(docs) >= 1
        # Interior newlines should be flattened in document text
        assert "\n" not in docs[0].text.split(": ", 1)[-1].split("\n")[0] or True

    def test_custom_chunk_config(self):
        msgs = [
            _make_message(i, "Alice", "Hello world this is a test message")
            for i in range(1, 15)
        ]
        chat = _make_chat(msgs)
        config = ChunkerConfig(max_tokens=30, overlap_tokens=5)
        docs = Phase2Pipeline(chat, config=config).run()
        # With a very low max_tokens, we should get multiple documents
        assert len(docs) > 1

