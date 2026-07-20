"""
tests/test_timestamp_filter.py — Phase 6+20: Timestamp post-filter tests.
Uses real RetrievedDocument objects with controlled metadata timestamps.
"""
from __future__ import annotations
import pytest
from datetime import datetime, timezone, timedelta
from app.retrieval.timestamp_filter import (
    apply_timestamp_postfilter, TimestampFilterConfig, _parse_metadata_timestamp
)
from models.retrieved_document import RetrievedDocument


def _doc(doc_id: str, timestamp: str | None, score: float = 0.9) -> RetrievedDocument:
    meta = {"source": "telegram", "owner_id": "o1"}
    if timestamp is not None:
        meta["timestamp"] = timestamp
    return RetrievedDocument(
        document_id=doc_id, text=f"text for {doc_id}",
        metadata=meta, distance=1.0 - score,
        similarity_score=score, rank=1,
        source_collection="test_col", query="q",
    )


UTC = timezone.utc
T_0959 = datetime(2026, 7, 14, 9, 59, 59, tzinfo=UTC)
T_1000 = datetime(2026, 7, 14, 10, 0, 0, tzinfo=UTC)
T_1030 = datetime(2026, 7, 14, 10, 30, 0, tzinfo=UTC)
T_1100 = datetime(2026, 7, 14, 11, 0, 0, tzinfo=UTC)
T_1101 = datetime(2026, 7, 14, 11, 0, 1, tzinfo=UTC)


@pytest.fixture()
def docs():
    return [
        _doc("d1", T_0959.isoformat(), 0.95),
        _doc("d2", T_1000.isoformat(), 0.90),
        _doc("d3", T_1030.isoformat(), 0.85),
        _doc("d4", T_1100.isoformat(), 0.80),
        _doc("d5", T_1101.isoformat(), 0.75),
    ]


# ===========================================================================
# No-filter pass-through (REFACTOR-SAFE regression)
# ===========================================================================

class TestNoFilterPassThrough:
    def test_no_filter_returns_top_k_unchanged(self, docs):
        result = apply_timestamp_postfilter(docs, None, None, top_k=3)
        assert len(result) == 3
        assert result[0].document_id == "d1"
        assert result[1].document_id == "d2"
        assert result[2].document_id == "d3"

    def test_no_filter_same_object_references(self, docs):
        """Regression: no-filter path returns the same objects, no mutation."""
        result = apply_timestamp_postfilter(docs, None, None, top_k=10)
        for orig, res in zip(docs, result):
            assert orig is res


# ===========================================================================
# timestamp_from only
# ===========================================================================

class TestTimestampFrom:
    def test_from_excludes_earlier(self, docs):
        result = apply_timestamp_postfilter(docs, T_1000, None, top_k=10)
        ids = [r.document_id for r in result]
        assert "d1" not in ids  # 09:59 < 10:00
        assert "d2" in ids
        assert "d3" in ids

    def test_from_inclusive_exact_boundary(self, docs):
        result = apply_timestamp_postfilter(docs, T_1000, None, top_k=10)
        assert any(r.document_id == "d2" for r in result)


# ===========================================================================
# timestamp_to only
# ===========================================================================

class TestTimestampTo:
    def test_to_excludes_later(self, docs):
        result = apply_timestamp_postfilter(docs, None, T_1100, top_k=10)
        ids = [r.document_id for r in result]
        assert "d5" not in ids  # 11:00:01 > 11:00:00
        assert "d4" in ids

    def test_to_inclusive_exact_boundary(self, docs):
        result = apply_timestamp_postfilter(docs, None, T_1100, top_k=10)
        assert any(r.document_id == "d4" for r in result)


# ===========================================================================
# Both bounds
# ===========================================================================

class TestBothBounds:
    def test_both_bounds_narrow_window(self, docs):
        result = apply_timestamp_postfilter(docs, T_1000, T_1100, top_k=10)
        ids = [r.document_id for r in result]
        assert "d1" not in ids
        assert "d2" in ids
        assert "d3" in ids
        assert "d4" in ids
        assert "d5" not in ids

    def test_both_bounds_top_k_respected(self, docs):
        result = apply_timestamp_postfilter(docs, T_1000, T_1100, top_k=2)
        assert len(result) == 2


# ===========================================================================
# Timezone normalization
# ===========================================================================

class TestTimezoneNormalization:
    def test_ist_offset_normalized_correctly(self):
        """10:00 UTC and 15:30 IST (+05:30) represent the same instant."""
        utc_doc = _doc("utc", "2026-07-14T10:00:00+00:00", 0.9)
        ist_doc = _doc("ist", "2026-07-14T15:30:00+05:30", 0.85)
        docs = [utc_doc, ist_doc]
        result = apply_timestamp_postfilter(docs, T_1000, T_1100, top_k=10)
        ids = [r.document_id for r in result]
        assert "utc" in ids
        assert "ist" in ids

    def test_z_suffix_treated_as_utc(self):
        doc = _doc("z", "2026-07-14T10:30:00Z", 0.9)
        result = apply_timestamp_postfilter([doc], T_1000, T_1100, top_k=10)
        assert result[0].document_id == "z"


# ===========================================================================
# Invalid / missing timestamps
# ===========================================================================

class TestInvalidTimestamps:
    def test_invalid_timestamp_excluded_when_filter_active(self):
        bad = _doc("bad", "not-a-date", 0.99)
        good = _doc("good", T_1030.isoformat(), 0.85)
        result = apply_timestamp_postfilter([bad, good], T_1000, T_1100, top_k=10)
        ids = [r.document_id for r in result]
        assert "bad" not in ids
        assert "good" in ids

    def test_missing_timestamp_excluded_when_filter_active(self):
        no_ts = _doc("nots", None, 0.99)
        good = _doc("good", T_1030.isoformat(), 0.85)
        result = apply_timestamp_postfilter([no_ts, good], T_1000, T_1100, top_k=10)
        assert not any(r.document_id == "nots" for r in result)

    def test_invalid_timestamp_does_not_crash(self):
        bad = _doc("bad", "2026-99-99T99:99:99", 0.99)
        result = apply_timestamp_postfilter([bad], T_1000, T_1100, top_k=10)
        assert result == []


# ===========================================================================
# Similarity order preserved
# ===========================================================================

class TestOrderPreserved:
    def test_similarity_order_preserved_after_filter(self, docs):
        result = apply_timestamp_postfilter(docs, T_1000, T_1100, top_k=10)
        scores = [r.similarity_score for r in result]
        assert scores == sorted(scores, reverse=True)


# ===========================================================================
# _parse_metadata_timestamp unit tests
# ===========================================================================

class TestParseMetadataTimestamp:
    def test_none_returns_none(self):
        assert _parse_metadata_timestamp(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_metadata_timestamp("") is None

    def test_datetime_aware_returned_as_utc(self):
        dt = datetime(2026, 7, 14, 10, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        result = _parse_metadata_timestamp(dt)
        assert result.tzinfo == UTC
        assert result.hour == 4  # 10:00 IST = 04:30 UTC

    def test_datetime_naive_gets_utc(self):
        dt = datetime(2026, 7, 14, 10, 0)
        result = _parse_metadata_timestamp(dt)
        assert result.tzinfo == UTC

    def test_iso_string_with_offset(self):
        result = _parse_metadata_timestamp("2026-07-14T15:30:00+05:30")
        assert result is not None
        assert result.tzinfo == UTC
        assert result.hour == 10  # 15:30 IST = 10:00 UTC

    def test_z_suffix(self):
        result = _parse_metadata_timestamp("2026-07-14T10:00:00Z")
        assert result is not None
        assert result.hour == 10
