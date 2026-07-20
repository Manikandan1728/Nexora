"""
app/retrieval/snippet_extraction.py — Query-focused snippet extraction (Phase 5B).

WHAT THIS MODULE DOES
---------------------
Pure-function layer. Given a raw query string and a full chunk text, it:

  1. Segments the chunk into individual messages using timestamp-prefixed
     line patterns from utils/message_patterns.py. Falls back to
     newline-based splitting when no boundaries are detected — flagged via
     SnippetResult.fallback_split.

  2. Prepares query terms: lowercase, strip punctuation, remove stopwords.

  3. Scores each message on two signals:
       exact_score  — whole-word case-insensitive match count × EXACT_WEIGHT
       partial_score — substring match count × PARTIAL_WEIGHT

  4. Applies exact-match boosting: messages with exact_score > 0 rank above
     all messages with exact_score == 0.

  5. Includes ±1 neighbours deterministically.

  6. Caps the selection at SNIPPET_LINE_CAP lines, re-sorts chronologically.

  7. Returns a SnippetResult with all required fields.

CONFIG
------
SNIPPET_LINE_CAP and SEMANTIC_OVERRIDE_MARGIN live in config/snippet_config.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

from app.retrieval.query_preprocessor import QueryPreprocessor
from config.snippet_config import SEMANTIC_OVERRIDE_MARGIN, SNIPPET_LINE_CAP
from utils.message_patterns import SENDER_MESSAGE_PATTERN, SYSTEM_MESSAGE_PATTERN

# ---------------------------------------------------------------------------
# Scoring weights (kept local — not a tunable user config, just constants)
# ---------------------------------------------------------------------------
_EXACT_WEIGHT: int = 10    # whole-word case-insensitive match
_PARTIAL_WEIGHT: int = 2   # substring (non-whole-word) match

# ---------------------------------------------------------------------------
# Minimal English stopwords — no new NLP dependency
# ---------------------------------------------------------------------------
_STOPWORDS: Set[str] = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "with", "is", "are", "was", "were", "it", "this", "that", "of", "by",
    "as", "be", "from", "i", "my", "we", "you", "he", "she", "they",
    "me", "him", "her", "us", "do", "did", "have", "had", "not", "so",
    "if", "can", "will", "just", "about", "up", "out", "its",
}


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------

@dataclass
class MessageRef:
    """
    A verbatim single message extracted from the chunk.

    Attributes
    ----------
    text : str
        The full verbatim text of the message.
    index : int
        Zero-based index of this message within the segmented message list.
    """
    text: str
    index: int


@dataclass
class SnippetResult:
    """
    Output of extract_snippet().

    Attributes
    ----------
    focused_snippet : Optional[str]
        Verbatim lines joined with newlines, or None when no match found.
    matched_messages : Optional[List[MessageRef]]
        The MessageRef objects whose text appears in focused_snippet
        (only messages with score > 0 — neighbours are excluded from this list).
    matched_terms : Optional[List[str]]
        The query terms that produced at least one exact or partial match.
    relevance_reason : Optional[str]
        Template-built (not model-generated) explanation string.
    no_strong_passage : bool
        True when the extractor found zero messages with any exact or partial
        match for the query terms.  focused_snippet will be None in this case.
    fallback_split : bool
        True when no timestamp-prefixed message boundaries were detected and
        newline-based splitting was used instead.  Snippet precision is
        lower in this mode.
    """
    focused_snippet: Optional[str] = None
    matched_messages: Optional[List[MessageRef]] = None
    matched_terms: Optional[List[str]] = None
    relevance_reason: Optional[str] = None
    no_strong_passage: bool = False
    fallback_split: bool = False
    # True when no timestamp-prefixed message boundaries were detected and
    # newline-based splitting was used instead.


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_snippet(query: str, chunk_text: str) -> SnippetResult:
    """
    Extract a query-focused snippet from chunk_text.

    The function is a pure function — it never modifies chunk_text.

    Semantic override note
    ----------------------
    The SEMANTIC_OVERRIDE_MARGIN constant (config/snippet_config.py) is
    intentionally never evaluated here.  Per-message semantic scoring would
    require a model inference call for every message in every retrieved chunk,
    which adds unacceptable latency.  Exact-match always wins.  The override
    path will only be unlocked in a future version when cheap cached per-message
    embeddings are available.

    Args:
        query:      The user's raw query string.
        chunk_text: Full verbatim text of the retrieved chunk.

    Returns:
        SnippetResult.  Never raises; edge cases return safe defaults.
    """
    # ── Guard: empty inputs ───────────────────────────────────────────────────
    if not chunk_text or not chunk_text.strip():
        return SnippetResult(no_strong_passage=True)

    # ── Step 1: Message segmentation ─────────────────────────────────────────
    raw_lines = chunk_text.splitlines()
    messages, fallback_split = _segment_messages(raw_lines)

    if not messages:
        return SnippetResult(no_strong_passage=True, fallback_split=fallback_split)

    # ── Step 2: Query term preparation ───────────────────────────────────────
    try:
        clean_query = QueryPreprocessor.preprocess(query)
    except Exception:
        clean_query = query

    raw_terms = re.findall(r'\b\w+\b', clean_query.lower())
    query_terms = [t for t in raw_terms if t not in _STOPWORDS and len(t) > 1]

    if not query_terms:
        return SnippetResult(no_strong_passage=True, fallback_split=fallback_split)

    # ── Step 3: Per-message scoring ───────────────────────────────────────────
    exact_scores: List[int] = []
    partial_scores: List[int] = []

    for msg in messages:
        msg_lower = msg.lower()
        ex = 0
        pa = 0
        for term in query_terms:
            escaped = re.escape(term)
            word_count = len(re.findall(rf'\b{escaped}\b', msg_lower))
            if word_count > 0:
                ex += word_count
            else:
                if term in msg_lower:
                    pa += 1
        exact_scores.append(ex)
        partial_scores.append(pa)

    # Combined weighted score (for ranking within the same tier)
    combined_scores = [
        ex * _EXACT_WEIGHT + pa * _PARTIAL_WEIGHT
        for ex, pa in zip(exact_scores, partial_scores)
    ]

    if max(combined_scores) == 0:
        return SnippetResult(
            no_strong_passage=True,
            fallback_split=fallback_split,
        )

    # ── Step 4: Exact-match boosting ─────────────────────────────────────────
    # Messages with exact_score > 0 are ranked above exact_score == 0 messages.
    # Semantic override: NOT implemented (semantic_score is always None).
    # The SEMANTIC_OVERRIDE_MARGIN constant is imported but never evaluated here.
    # This comment documents the intentional omission per spec §1(d).
    _ = SEMANTIC_OVERRIDE_MARGIN  # referenced to satisfy import; never evaluated

    # ── Step 5: Neighbour inclusion ───────────────────────────────────────────
    selected_indices: Set[int] = set()
    for i, (ex, pa) in enumerate(zip(exact_scores, partial_scores)):
        if ex > 0 or pa > 0:
            selected_indices.add(i)
            msg_tokens = _content_tokens(messages[i])

            # Previous neighbour (±1 only)
            if i > 0 and (exact_scores[i - 1] == 0 and partial_scores[i - 1] == 0):
                prev_tokens = _content_tokens(messages[i - 1])
                if (msg_tokens & prev_tokens) - _STOPWORDS:
                    selected_indices.add(i - 1)

            # Next neighbour (±1 only)
            if i < len(messages) - 1 and (
                exact_scores[i + 1] == 0 and partial_scores[i + 1] == 0
            ):
                next_tokens = _content_tokens(messages[i + 1])
                if (msg_tokens & next_tokens) - _STOPWORDS:
                    selected_indices.add(i + 1)

    # ── Step 6: Selection and cap ─────────────────────────────────────────────
    # Sort candidates: exact-match messages first (descending combined_score),
    # then neighbours (which have combined_score == 0) by index.
    scored_candidates = sorted(
        selected_indices,
        key=lambda idx: (-combined_scores[idx], idx),
    )

    final_indices: List[int] = []
    total_lines = 0

    for idx in scored_candidates:
        msg_line_count = len(messages[idx].splitlines()) or 1
        if total_lines == 0 and msg_line_count > SNIPPET_LINE_CAP:
            # Must include the top-scored message even if it exceeds cap
            final_indices.append(idx)
            total_lines += msg_line_count
            break
        if total_lines + msg_line_count <= SNIPPET_LINE_CAP:
            final_indices.append(idx)
            total_lines += msg_line_count
        # else: skip — doesn't fit within cap

    if not final_indices:
        return SnippetResult(
            no_strong_passage=True,
            fallback_split=fallback_split,
        )

    # Restore chronological order
    final_indices.sort()

    # ── Step 7: Build output ──────────────────────────────────────────────────
    snippet_lines: List[str] = []
    matched_messages: List[MessageRef] = []

    for idx in final_indices:
        raw_msg = messages[idx]
        # Enforce per-message line cap only when the single message is the
        # only one selected and exceeds SNIPPET_LINE_CAP
        msg_lines = raw_msg.splitlines()
        if len(snippet_lines) + len(msg_lines) > SNIPPET_LINE_CAP and snippet_lines:
            break
        lines_to_add = msg_lines[: SNIPPET_LINE_CAP - len(snippet_lines)]
        snippet_lines.extend(lines_to_add)

        if combined_scores[idx] > 0:
            matched_messages.append(
                MessageRef(text="\n".join(lines_to_add), index=idx)
            )

    focused_snippet = "\n".join(snippet_lines) if snippet_lines else None

    # Determine which query terms actually matched
    matched_terms: List[str] = []
    for term in query_terms:
        escaped = re.escape(term)
        for msg in messages:
            if re.search(rf'\b{escaped}\b', msg.lower()) or term in msg.lower():
                if term not in matched_terms:
                    matched_terms.append(term)
                break

    # Build relevance_reason — template-driven, not model-generated
    total_exact = sum(exact_scores[i] for i in final_indices if combined_scores[i] > 0)
    total_partial = sum(partial_scores[i] for i in final_indices if combined_scores[i] > 0)

    reason_parts: List[str] = []
    if matched_terms:
        top_term = matched_terms[0]
        # Count occurrences of the top term in the focused snippet
        top_count = sum(exact_scores[i] for i in final_indices)
        if top_count > 0:
            reason_parts.append(
                f"Matched keyword: {top_term!r} ({top_count} occurrence{'s' if top_count != 1 else ''})"
            )
        if len(matched_terms) > 1:
            others = ", ".join(repr(t) for t in matched_terms[1:])
            reason_parts.append(f"also matched: {others}")
    if total_partial > 0 and total_exact == 0:
        reason_parts.append(f"Substring match ({total_partial} occurrence{'s' if total_partial != 1 else ''})")

    relevance_reason = "; ".join(reason_parts) if reason_parts else None

    return SnippetResult(
        focused_snippet=focused_snippet,
        matched_messages=matched_messages if matched_messages else None,
        matched_terms=matched_terms if matched_terms else None,
        relevance_reason=relevance_reason,
        no_strong_passage=False,
        fallback_split=fallback_split,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _segment_messages(lines: list[str]) -> tuple[list[str], bool]:
    """
    Group raw text lines into logical messages using timestamp-prefixed patterns.

    Uses SENDER_MESSAGE_PATTERN / SYSTEM_MESSAGE_PATTERN from
    utils/message_patterns.py.

    Returns
    -------
    (messages, fallback_split)
        messages       : list of message strings (may be multi-line each)
        fallback_split : True when no timestamp boundaries were found
    """
    has_boundaries = any(
        SENDER_MESSAGE_PATTERN.match(line) or SYSTEM_MESSAGE_PATTERN.match(line)
        for line in lines
    )

    if not has_boundaries:
        # Fallback: each non-empty line is its own "message"
        return (
            [line for line in lines if line.strip()],
            True,
        )

    messages: List[str] = []
    current: List[str] = []

    for line in lines:
        if SENDER_MESSAGE_PATTERN.match(line) or SYSTEM_MESSAGE_PATTERN.match(line):
            if current:
                messages.append("\n".join(current))
            current = [line]
        else:
            if not current:
                current = [line]
            else:
                current.append(line)

    if current:
        messages.append("\n".join(current))

    return messages, False


def _content_tokens(message: str) -> Set[str]:
    """
    Extract meaningful word tokens from a message for neighbour comparison.

    Strips the timestamp/sender prefix to avoid matching on sender
    names or timestamps rather than message content.
    """
    # Try to strip sender prefix
    m = SENDER_MESSAGE_PATTERN.match(message)
    if m:
        text = m.group("body")
    else:
        sm = SYSTEM_MESSAGE_PATTERN.match(message)
        if sm:
            text = sm.group("body")
        else:
            text = message

    # Only alphabetic tokens of length ≥ 3
    return set(re.findall(r'\b[a-z]{3,}\b', text.lower()))
