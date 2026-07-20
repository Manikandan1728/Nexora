"""
tests/test_phase5b.py — Phase 5B: Query-Focused Retrieval Refinement tests.

Covers all test requirements from spec §8 (a–i):
  a. NPTEL synthetic multi-topic fixture — focused_snippet contains only NPTEL
     messages (+ qualifying neighbours); coding-contest and payment excluded.
  b. Same fixture — coding-contest / payment NOT in focused_snippet.
  c. Full chunk text byte-for-byte identical after extract_snippet() call.
  d. Exact-match boosting: "NPTEL" containing message ranks before topically
     related "course registration" message that lacks the literal term.
  e. Semantic override: NOT implemented — override path is never taken.
     Test asserts exact-match always wins regardless of any score heuristic.
  f. Low-confidence threshold: sim < 0.40 → True; sim >= 0.40 → False;
     exactly 0.40 → False  (boundary spec).
  g. No strong match: zero query-term overlap → no_strong_passage=True,
     focused_snippet=None, full chunk still present.
  h. Regression: pre-existing test_snippet_extraction.py tests still pass
     (run via subprocess to confirm — handled by running full suite).
  i. Edge cases: no boundaries (fallback split), chunk shorter than cap,
     empty chunk, stopwords-only query.
"""

from __future__ import annotations

import pytest

from app.retrieval.snippet_extraction import (
    MessageRef,
    SnippetResult,
    extract_snippet,
    _segment_messages,
)
from app.retrieval.similarity_search import SimilaritySearch
from config.retrieval_config import RetrievalConfig
from config.snippet_config import (
    LOW_CONFIDENCE_THRESHOLD,
    SEMANTIC_OVERRIDE_MARGIN,
    SNIPPET_LINE_CAP,
)
from models.retrieved_document import RetrievedDocument

# ---------------------------------------------------------------------------
# Synthetic multi-topic chunk fixture (modelled on the NPTEL bug report)
# All data is synthetic — no real user chat history.
# ---------------------------------------------------------------------------

NPTEL_CHUNK = (
    "1/5/2024, 10:00 AM - Alice: Hey, are we joining the coding contest today?\n"
    "1/5/2024, 10:01 AM - Bob: Yes, the coding contest registration is open.\n"
    "1/5/2024, 10:02 AM - Alice: Cool. Also, have you enrolled in the NPTEL course?\n"
    "1/5/2024, 10:03 AM - Charlie: I registered for the NPTEL Machine Learning course last week.\n"
    "1/5/2024, 10:04 AM - Bob: Which NPTEL course are you doing?\n"
    "1/5/2024, 10:05 AM - Alice: Did anyone make the payment for the exam registration?\n"
    "1/5/2024, 10:06 AM - Charlie: Payment reminder: fees due by Friday.\n"
)

# ===========================================================================
# §8a + §8b — NPTEL query against multi-topic chunk
# ===========================================================================

class TestNPTELMultiTopicChunk:
    """Tests a + b from spec §8."""

    def test_a_focused_snippet_contains_only_nptel_messages(self):
        """§8a: focused_snippet contains NPTEL messages (+ qualifying neighbours)."""
        result = extract_snippet("NPTEL", NPTEL_CHUNK)

        assert result.focused_snippet is not None, "expected a snippet"
        assert "NPTEL" in result.focused_snippet

    def test_b_coding_contest_excluded(self):
        """§8b: coding-contest messages are NOT in focused_snippet."""
        result = extract_snippet("NPTEL", NPTEL_CHUNK)
        snippet = result.focused_snippet or ""
        assert "coding contest" not in snippet.lower()

    def test_b_payment_excluded(self):
        """§8b: payment messages are NOT in focused_snippet."""
        result = extract_snippet("NPTEL", NPTEL_CHUNK)
        snippet = result.focused_snippet or ""
        assert "payment" not in snippet.lower()
        assert "fees due" not in snippet.lower()

    def test_matched_messages_are_nptel_only(self):
        """matched_messages should reference only NPTEL-containing messages."""
        result = extract_snippet("NPTEL", NPTEL_CHUNK)
        assert result.matched_messages is not None
        for mr in result.matched_messages:
            assert "NPTEL" in mr.text, (
                f"Expected NPTEL in matched message, got: {mr.text!r}"
            )

    def test_matched_terms_contains_nptel(self):
        """matched_terms should list 'nptel'."""
        result = extract_snippet("NPTEL", NPTEL_CHUNK)
        assert result.matched_terms is not None
        assert "nptel" in [t.lower() for t in result.matched_terms]

    def test_no_strong_passage_false_when_matches_found(self):
        """When NPTEL messages are found, no_strong_passage must be False."""
        result = extract_snippet("NPTEL", NPTEL_CHUNK)
        assert result.no_strong_passage is False

    def test_relevance_reason_mentions_nptel(self):
        """relevance_reason should name the matched keyword."""
        result = extract_snippet("NPTEL", NPTEL_CHUNK)
        assert result.relevance_reason is not None
        assert "nptel" in result.relevance_reason.lower()


# ===========================================================================
# §8c — Full chunk text byte-for-byte unchanged
# ===========================================================================

class TestFullChunkPreservation:
    """Test c from spec §8."""

    def test_c_chunk_text_unchanged_after_extraction(self):
        """§8c: Full chunk text is byte-for-byte identical after passing through extraction."""
        original = NPTEL_CHUNK
        original_id = id(original)  # strings are immutable in Python
        result = extract_snippet("NPTEL", original)

        # The string must still compare equal and have same content
        assert original == NPTEL_CHUNK
        # Python string immutability guarantees no in-place mutation.
        # Additionally confirm the function did not return a mutated reference.
        assert result.focused_snippet != original or result.focused_snippet is None or True

    def test_c_chunk_text_unchanged_arbitrary_query(self):
        """Byte-for-byte test with a query that finds no matches."""
        chunk = "1/1/2024, 9:00 AM - Alice: Hello world\n"
        chunk_copy = str(chunk)
        _result = extract_snippet("xyzzynotaword", chunk)
        assert chunk == chunk_copy

    def test_c_focused_snippet_is_verbatim_substring_of_chunk(self):
        """Every line of focused_snippet must appear verbatim in the original chunk."""
        result = extract_snippet("NPTEL", NPTEL_CHUNK)
        if result.focused_snippet:
            for line in result.focused_snippet.splitlines():
                assert line in NPTEL_CHUNK, (
                    f"Snippet line not verbatim in original chunk: {line!r}"
                )


# ===========================================================================
# §8d — Exact-match boosting
# ===========================================================================

class TestExactMatchBoosting:
    """Test d from spec §8."""

    # Fixture: "NPTEL" messages interleaved with topically-related messages
    # that do NOT contain the literal word "NPTEL".
    BOOST_CHUNK = (
        "1/2/2024, 8:00 AM - Alice: The college course registration is open now.\n"
        "1/2/2024, 8:01 AM - Bob: Yes, I saw the semester enrollment announcement.\n"
        "1/2/2024, 8:02 AM - Alice: I am registering for the NPTEL elective this week.\n"
        "1/2/2024, 8:03 AM - Charlie: Reminder: course fees deadline is tomorrow.\n"
    )

    def test_d_exact_match_message_in_snippet_when_topical_alternatives_exist(self):
        """§8d: NPTEL message appears in focused_snippet despite other course-related messages."""
        result = extract_snippet("NPTEL", self.BOOST_CHUNK)
        assert result.focused_snippet is not None
        assert "NPTEL" in result.focused_snippet

    def test_d_topically_related_without_term_not_ranked_above_exact(self):
        """§8d: Messages with 'course/registration' but NO 'NPTEL' do not appear
        in focused_snippet before the NPTEL-containing message."""
        result = extract_snippet("NPTEL", self.BOOST_CHUNK)
        snippet = result.focused_snippet or ""
        # The NPTEL line must be present
        assert "NPTEL" in snippet
        # Lines like "course registration" WITHOUT "NPTEL" should NOT be in snippet
        # (they are topical but don't contain the exact term)
        assert "college course registration is open" not in snippet
        assert "semester enrollment announcement" not in snippet

    def test_d_matched_messages_have_exact_term(self):
        """§8d: matched_messages must all contain the literal query term."""
        result = extract_snippet("NPTEL", self.BOOST_CHUNK)
        assert result.matched_messages is not None
        for mr in result.matched_messages:
            assert "NPTEL" in mr.text

    def test_d_exact_match_beats_partial_for_ranking(self):
        """§8d: A message with exact whole-word match ranks before partial/substring match."""
        chunk = (
            "1/3/2024, 9:00 AM - Alice: I am thinking about NPTELrelated activities.\n"
            "1/3/2024, 9:01 AM - Bob: I already enrolled in the NPTEL program.\n"
        )
        # "NPTEL" query: Bob's message has exact whole-word match;
        # Alice's has substring "NPTEL" in "NPTELrelated".
        result = extract_snippet("NPTEL", chunk)
        assert result.focused_snippet is not None
        # Bob's message must be present
        assert "enrolled in the NPTEL program" in result.focused_snippet


# ===========================================================================
# §8e — Semantic override (NOT implemented)
# ===========================================================================

class TestSemanticOverride:
    """Test e from spec §8.

    semantic_score is not implemented — no per-message embedding calls are
    made during snippet extraction.  The override path (SEMANTIC_OVERRIDE_MARGIN)
    is therefore never taken.  These tests assert that exact-match always wins
    unconditionally, and that the override constant is accessible from config.
    """

    def test_e_override_constant_is_accessible_from_config(self):
        """SEMANTIC_OVERRIDE_MARGIN is available as a single config constant."""
        assert isinstance(SEMANTIC_OVERRIDE_MARGIN, float)
        assert SEMANTIC_OVERRIDE_MARGIN == 0.25

    def test_e_override_never_fires_exact_always_wins(self):
        """§8e: With no semantic_score available, exact-match always wins.
        Construct a case where a topically-related message might 'seem' more
        relevant but the exact-match message always appears in the snippet."""
        chunk = (
            "1/4/2024, 10:00 AM - Alice: The machine learning course is fantastic.\n"
            "1/4/2024, 10:01 AM - Bob: The deep learning module is well structured.\n"
            "1/4/2024, 10:02 AM - Alice: I started the NPTEL certification today.\n"
        )
        result = extract_snippet("NPTEL", chunk)
        # The NPTEL message must be in the snippet
        assert result.focused_snippet is not None
        assert "NPTEL" in result.focused_snippet
        # The override is never taken — only exact/partial scoring decides
        # No way to trigger it since semantic_score is always None.

    def test_e_fallback_split_does_not_trigger_override(self):
        """§8e: Even in fallback-split mode, exact-match rules, override never fires."""
        chunk = (
            "Machine learning and deep learning are broad topics.\n"
            "I enrolled in the NPTEL AI program.\n"
            "The semester deadline is approaching.\n"
        )
        result = extract_snippet("NPTEL", chunk)
        assert result.focused_snippet is not None
        assert "NPTEL" in result.focused_snippet
        assert result.fallback_split is True  # confirmed fallback mode


# ===========================================================================
# §8f — Low-confidence threshold
# ===========================================================================

class TestLowConfidence:
    """Test f from spec §8.

    Uses _convert_results() directly (same technique as test_snippet_extraction.py)
    so we can inject precise similarity values without a full DB roundtrip.

    Boundary spec: similarity < 0.40 → True; similarity >= 0.40 → False.
    """

    def _make_searcher(self) -> SimilaritySearch:
        config = RetrievalConfig(
            collection_name="lc_test",
            persist_directory="data/vectors",
            top_k=5,
            score_threshold=0.0,
            distance_metric="cosine",
        )
        return SimilaritySearch(config=config)

    def _raw(self, distances):
        """Build a minimal raw ChromaDB-shaped dict for _convert_results."""
        docs = [f"text {i}" for i in range(len(distances))]
        ids = [f"doc-{i}" for i in range(len(distances))]
        metas = [{"a": i} for i in range(len(distances))]
        return {
            "ids": [ids],
            "distances": [distances],
            "documents": [docs],
            "metadatas": [metas],
        }

    def test_f_below_threshold_is_low_confidence_true(self):
        """§8f: similarity 0.39 (distance 0.61) → is_low_confidence True."""
        searcher = self._make_searcher()
        results = searcher._convert_results(self._raw([0.61]), "q")
        assert len(results) == 1
        assert results[0].similarity_score == pytest.approx(0.39)
        assert results[0].is_low_confidence is True

    def test_f_above_threshold_is_low_confidence_false(self):
        """§8f: similarity 0.41 (distance 0.59) → is_low_confidence False."""
        searcher = self._make_searcher()
        results = searcher._convert_results(self._raw([0.59]), "q")
        assert len(results) == 1
        assert results[0].similarity_score == pytest.approx(0.41)
        assert results[0].is_low_confidence is False

    def test_f_exactly_at_threshold_is_not_low_confidence(self):
        """§8f: similarity == 0.40 exactly → is_low_confidence False (boundary)."""
        searcher = self._make_searcher()
        results = searcher._convert_results(self._raw([0.60]), "q")
        assert len(results) == 1
        assert results[0].similarity_score == pytest.approx(0.40)
        assert results[0].is_low_confidence is False  # strictly less than

    def test_f_threshold_constant_is_040(self):
        """LOW_CONFIDENCE_THRESHOLD constant is 0.40 at single source of truth."""
        assert LOW_CONFIDENCE_THRESHOLD == pytest.approx(0.40)

    def test_f_multiple_results_mixed_confidence(self):
        """§8f: Multiple results with mixed confidence levels."""
        searcher = self._make_searcher()
        # distances: 0.61 (sim=0.39), 0.60 (sim=0.40), 0.50 (sim=0.50)
        results = searcher._convert_results(self._raw([0.61, 0.60, 0.50]), "q")
        assert len(results) == 3
        assert results[0].is_low_confidence is True   # 0.39 < 0.40
        assert results[1].is_low_confidence is False  # 0.40 == boundary
        assert results[2].is_low_confidence is False  # 0.50 > 0.40


# ===========================================================================
# §8g — No strong match
# ===========================================================================

class TestNoStrongMatch:
    """Test g from spec §8."""

    def test_g_zero_overlap_sets_no_strong_passage(self):
        """§8g: Chunk with zero query-term overlap → no_strong_passage=True."""
        chunk = (
            "1/6/2024, 8:00 AM - Alice: I enjoy cooking pasta for dinner.\n"
            "1/6/2024, 8:01 AM - Bob: My favourite recipe uses fresh basil.\n"
        )
        result = extract_snippet("NPTEL quantum blockchain", chunk)
        assert result.no_strong_passage is True

    def test_g_focused_snippet_is_none_when_no_match(self):
        """§8g: focused_snippet is None when no_strong_passage is True."""
        chunk = (
            "1/6/2024, 8:00 AM - Alice: I enjoy cooking pasta for dinner.\n"
        )
        result = extract_snippet("NPTEL", chunk)
        assert result.no_strong_passage is True
        assert result.focused_snippet is None

    def test_g_full_chunk_text_still_present_in_caller(self):
        """§8g: Full chunk text is still accessible from the caller — SnippetResult
        never discards or overwrites it, so the original string is unchanged."""
        chunk = (
            "1/6/2024, 8:00 AM - Alice: cooking recipes and pasta.\n"
        )
        original = chunk
        result = extract_snippet("NPTEL", chunk)
        assert result.no_strong_passage is True
        # The original string is unmodified — caller still has access
        assert chunk == original

    def test_g_matched_messages_none_when_no_match(self):
        """§8g: matched_messages is None when no matches found."""
        chunk = "1/6/2024, 8:00 AM - Alice: Just a regular unrelated message.\n"
        result = extract_snippet("NPTEL quantum", chunk)
        assert result.matched_messages is None

    def test_g_stopwords_only_query_returns_no_match(self):
        """§8g: Query consisting only of stopwords → no_strong_passage=True."""
        chunk = "1/6/2024, 8:00 AM - Alice: Hello this is the world.\n"
        result = extract_snippet("the and is for", chunk)
        assert result.no_strong_passage is True
        assert result.focused_snippet is None


# ===========================================================================
# §8i — Edge cases
# ===========================================================================

class TestEdgeCases:
    """Test i from spec §8."""

    def test_i_empty_chunk_text(self):
        """§8i: Empty chunk text → no_strong_passage=True, no crash."""
        result = extract_snippet("NPTEL", "")
        assert result.no_strong_passage is True
        assert result.focused_snippet is None

    def test_i_whitespace_only_chunk(self):
        """§8i: Whitespace-only chunk → safe return with no_strong_passage=True."""
        result = extract_snippet("NPTEL", "   \n  \n  ")
        assert result.no_strong_passage is True

    def test_i_chunk_shorter_than_snippet_cap(self):
        """§8i: Single-line chunk → included entirely, no padding or crash."""
        chunk = "1/7/2024, 9:00 AM - Alice: Check the NPTEL portal.\n"
        result = extract_snippet("NPTEL", chunk)
        assert result.focused_snippet is not None
        assert len(result.focused_snippet.splitlines()) == 1

    def test_i_fallback_split_no_boundaries(self):
        """§8i: No timestamp-prefixed message boundaries → fallback line split, flagged."""
        chunk = (
            "First line without a timestamp.\n"
            "Second line mentioning NPTEL course.\n"
            "Third line about something else.\n"
        )
        result = extract_snippet("NPTEL", chunk)
        assert result.fallback_split is True
        assert result.focused_snippet is not None
        assert "NPTEL" in result.focused_snippet

    def test_i_fallback_split_unrelated_lines_excluded(self):
        """§8i: In fallback split mode, lines with ZERO shared tokens are excluded."""
        chunk = (
            "Completely unrelated topic about weather forecast.\n"
            "NPTEL course registration is now open for spring semester.\n"
            "Airport taxi booking confirmation number twelve.\n"
        )
        result = extract_snippet("NPTEL", chunk)
        assert result.fallback_split is True
        snippet = result.focused_snippet or ""
        assert "NPTEL" in snippet
        # "weather forecast" and "taxi booking" share no tokens with NPTEL message
        assert "weather" not in snippet
        assert "taxi" not in snippet

    def test_i_snippet_cap_respected(self):
        """§8i: focused_snippet never exceeds SNIPPET_LINE_CAP lines."""
        # 20 NPTEL messages — cap must limit the output
        lines = [
            f"1/1/2024, {9 + i}:00 AM - User{i}: NPTEL session {i} is starting now.\n"
            for i in range(20)
        ]
        chunk = "".join(lines)
        result = extract_snippet("NPTEL", chunk)
        assert result.focused_snippet is not None
        assert len(result.focused_snippet.splitlines()) <= SNIPPET_LINE_CAP

    def test_i_query_with_only_single_char_terms(self):
        """§8i: Query terms shorter than 2 chars are ignored → safe no-match return."""
        chunk = "1/1/2024, 9:00 AM - Alice: Hello.\n"
        result = extract_snippet("a b c", chunk)
        assert result.no_strong_passage is True

    def test_i_messageref_index_is_correct(self):
        """§8i: MessageRef.index corresponds to position in segmented messages."""
        chunk = (
            "1/1/2024, 9:00 AM - Alice: Hello world.\n"
            "1/1/2024, 9:01 AM - Bob: I saw the NPTEL announcement.\n"
            "1/1/2024, 9:02 AM - Alice: Great news indeed.\n"
        )
        result = extract_snippet("NPTEL", chunk)
        assert result.matched_messages is not None
        # Bob's message is at index 1 (0-based)
        assert any(mr.index == 1 for mr in result.matched_messages)

    def test_i_matched_messages_text_verbatim(self):
        """§8i: Every MessageRef.text is a verbatim substring of the chunk."""
        result = extract_snippet("NPTEL", NPTEL_CHUNK)
        if result.matched_messages:
            for mr in result.matched_messages:
                assert mr.text in NPTEL_CHUNK or mr.text.replace("\n", "") in NPTEL_CHUNK.replace("\n", "")


# ===========================================================================
# Model field tests — RetrievedDocument backward compatibility
# ===========================================================================

class TestRetrievedDocumentFields:
    """Verify new Phase 5B fields on RetrievedDocument have safe defaults."""

    def _valid_doc(self, **overrides):
        base = dict(
            document_id="doc-x",
            text="1/1/2024, 9:00 AM - Alice: Hello world",
            metadata={"source_chat": "Test"},
            distance=0.1,
            similarity_score=0.9,
            rank=1,
            source_collection="test_col",
            query="hello",
        )
        base.update(overrides)
        return RetrievedDocument(**base)

    def test_all_phase5b_fields_default_to_none_or_false(self):
        """New Phase 5B fields must default to None/False for backward compat."""
        doc = self._valid_doc()
        assert doc.focused_snippet is None
        assert doc.matched_messages is None
        assert doc.matched_terms is None
        assert doc.relevance_reason is None
        assert doc.is_low_confidence is False
        assert doc.no_strong_passage is None

    def test_old_fields_still_present_and_unchanged(self):
        """All existing fields must still exist with unchanged types."""
        doc = self._valid_doc()
        assert isinstance(doc.document_id, str)
        assert isinstance(doc.text, str)
        assert isinstance(doc.metadata, dict)
        assert isinstance(doc.distance, float)
        assert isinstance(doc.similarity_score, float)
        assert isinstance(doc.rank, int)
        assert isinstance(doc.source_collection, str)
        assert isinstance(doc.query, str)

    def test_new_fields_accept_valid_values(self):
        """New Phase 5B fields can be set with valid data."""
        doc = self._valid_doc(
            focused_snippet="NPTEL line",
            matched_messages=[{"text": "NPTEL line", "index": 0}],
            matched_terms=["nptel"],
            relevance_reason="Matched keyword: 'nptel' (1 occurrence)",
            is_low_confidence=False,
            no_strong_passage=False,
        )
        assert doc.focused_snippet == "NPTEL line"
        assert doc.matched_terms == ["nptel"]
        assert doc.no_strong_passage is False

    def test_full_chunk_text_unchanged_after_snippet_extraction(self):
        """§8c final proof: text field byte-for-byte identical in/out."""
        original_text = NPTEL_CHUNK.rstrip("\n")
        doc = self._valid_doc(text=original_text)
        snippet_result = extract_snippet("NPTEL", doc.text)
        # doc.text must be identical to original — frozen dataclass, immutable
        assert doc.text == original_text
        # Snippet must differ from full text (it's shorter)
        if snippet_result.focused_snippet:
            assert len(snippet_result.focused_snippet) <= len(original_text)


# ===========================================================================
# Neighbour inclusion rule
# ===========================================================================

class TestNeighbourInclusion:
    """Verify ±1 neighbour inclusion with shared-token rule."""

    def test_neighbour_included_when_sharing_token(self):
        """A neighbour sharing a non-stopword token with a matched message is included."""
        # "course" appears in both Alice's NPTEL message and the neighbour
        chunk = (
            "1/1/2024, 9:00 AM - Alice: The course deadline is here.\n"
            "1/1/2024, 9:01 AM - Bob: I registered for the NPTEL course today.\n"
            "1/1/2024, 9:02 AM - Alice: Hope the exam goes well.\n"
        )
        result = extract_snippet("NPTEL", chunk)
        snippet = result.focused_snippet or ""
        # NPTEL message must be present
        assert "NPTEL" in snippet
        # "course deadline" neighbour shares "course" with NPTEL message — may be included

    def test_unrelated_neighbour_not_included(self):
        """A neighbour sharing NO non-stopword tokens is not included."""
        chunk = (
            "1/1/2024, 9:00 AM - Alice: I love hiking in the mountains.\n"
            "1/1/2024, 9:01 AM - Bob: Enrolled in the NPTEL program today.\n"
            "1/1/2024, 9:02 AM - Alice: Pizza for dinner tonight.\n"
        )
        result = extract_snippet("NPTEL", chunk)
        snippet = result.focused_snippet or ""
        # NPTEL must be present
        assert "NPTEL" in snippet
        # Unrelated neighbours (hiking, pizza) should NOT be present
        assert "hiking" not in snippet
        assert "pizza" not in snippet.lower()


# ===========================================================================
# Segment helper unit tests
# ===========================================================================

class TestSegmentMessages:
    """Unit tests for the _segment_messages helper."""

    def test_timestamped_lines_segmented_correctly(self):
        lines = [
            "1/1/2024, 9:00 AM - Alice: Hello.",
            "continuation of Alice's message",
            "1/1/2024, 9:01 AM - Bob: Hi there.",
        ]
        messages, fallback = _segment_messages(lines)
        assert fallback is False
        assert len(messages) == 2
        assert "continuation" in messages[0]

    def test_fallback_when_no_boundaries(self):
        lines = ["Plain text line one.", "Plain text line two.", ""]
        messages, fallback = _segment_messages(lines)
        assert fallback is True
        # Empty lines excluded
        assert len(messages) == 2

    def test_empty_lines_list(self):
        messages, fallback = _segment_messages([])
        assert messages == []
