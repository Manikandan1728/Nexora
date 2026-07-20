"""
app/retrieval/timestamp_filter.py

[ADDITIVE] Application-level timestamp post-filter for retrieval.

WHY THIS EXISTS
---------------
ChromaDB 1.5.9 stores timestamps as ISO-8601 strings and compares them
lexicographically. This is only reliable for UTC-normalized timestamps
with a consistent format. When timestamps have mixed offsets (+05:30, Z,
+00:00) or inconsistent formats, string comparison produces wrong results.

This module applies an accurate, inclusive datetime comparison AFTER
ChromaDB retrieval, on the similarity-ranked candidate set.

CONFIGURATION
-------------
timestamp_candidate_multiplier: int = 4  (default)
timestamp_min_candidates: int = 20
timestamp_max_candidates: int = 200

These are read from TimestampFilterConfig, injectable for tests.

BEHAVIOR
--------
- When NO timestamp filter is active, this module is a no-op pass-through
  (result set and order are byte-for-byte unchanged — REFACTOR-SAFE).
- When a timestamp filter IS active:
    1. Candidate set is fetched from ChromaDB with expanded top_k.
    2. Each candidate's timestamp metadata is parsed to timezone-aware UTC.
    3. Inclusive timestamp_from / timestamp_to bounds are applied.
    4. Similarity order is preserved in the filtered result.
    5. Final top_k is returned.
- Invalid or missing timestamps in candidate metadata: excluded when
  a filter is active (never crash, just exclude).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from models.retrieved_document import RetrievedDocument

logger = logging.getLogger(__name__)


@dataclass
class TimestampFilterConfig:
    """Configuration for candidate expansion and post-filtering."""
    candidate_multiplier: int = 4
    min_candidates: int = 20
    max_candidates: int = 200

    def candidate_k(self, top_k: int) -> int:
        """Calculate how many candidates to fetch from ChromaDB."""
        raw = max(top_k * self.candidate_multiplier, self.min_candidates)
        return min(raw, self.max_candidates)


def apply_timestamp_postfilter(
    results: list[RetrievedDocument],
    timestamp_from: Optional[datetime],
    timestamp_to: Optional[datetime],
    top_k: int,
    config: TimestampFilterConfig | None = None,
) -> list[RetrievedDocument]:
    """
    Apply inclusive timestamp post-filtering to a ranked result set.

    Args:
        results:        Similarity-ranked RetrievedDocument list from ChromaDB.
        timestamp_from: Inclusive lower bound (timezone-aware datetime or None).
        timestamp_to:   Inclusive upper bound (timezone-aware datetime or None).
        top_k:          Maximum results to return after filtering.
        config:         Candidate expansion config. Uses defaults if None.

    Returns:
        Filtered list, preserving similarity order, capped at top_k.
        If no timestamp filter is active, returns results[:top_k] unchanged.

    Contract:
        When timestamp_from is None AND timestamp_to is None, this function
        returns results[:top_k] with ZERO mutations — same order, same objects.
        This is verified by test_timestamp_no_filter_is_noop().
    """
    # No filter active — pure pass-through (REFACTOR-SAFE branch)
    if timestamp_from is None and timestamp_to is None:
        return results[:top_k]

    cfg = config or TimestampFilterConfig()
    filtered: list[RetrievedDocument] = []

    for doc in results:
        ts = _parse_metadata_timestamp(doc.metadata.get("timestamp"))
        if ts is None:
            # Invalid or missing timestamp — exclude when filter is active
            logger.debug(
                "timestamp_postfilter: excluding doc=%r (unparseable timestamp)",
                doc.document_id,
            )
            continue

        if timestamp_from is not None and ts < timestamp_from:
            continue
        if timestamp_to is not None and ts > timestamp_to:
            continue

        filtered.append(doc)
        if len(filtered) >= top_k:
            break

    logger.info(
        "timestamp_postfilter: %d/%d candidates passed filter "
        "(from=%s to=%s top_k=%d)",
        len(filtered), len(results),
        timestamp_from.isoformat() if timestamp_from else None,
        timestamp_to.isoformat() if timestamp_to else None,
        top_k,
    )
    return filtered


def _parse_metadata_timestamp(raw: object) -> datetime | None:
    """
    Parse a timestamp value from ChromaDB metadata to a timezone-aware UTC datetime.

    Supports:
      - datetime objects (already aware or naive → treated as UTC)
      - ISO-8601 strings with or without timezone info
      - Strings ending in Z (UTC)
      - Returns None for None, empty string, or unparseable values
    """
    if raw is None:
        return None
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc)
        return raw.astimezone(timezone.utc)
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        # Normalize Z → +00:00 for fromisoformat compatibility
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (ValueError, TypeError):
            return None
    return None
