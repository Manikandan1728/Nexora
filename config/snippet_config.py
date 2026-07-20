"""
config/snippet_config.py — Configuration constants for Phase 5B snippet extraction.

Single source of truth for all tunable constants used by
app/retrieval/snippet_extraction.py.

SEMANTIC_OVERRIDE_MARGIN
    The minimum amount by which a candidate message's semantic_score must
    exceed the highest exact-match message's semantic_score before the
    override fires and the non-exact-match message can be ranked ahead.
    Only evaluated when semantic_score is available (currently: NEVER,
    since no per-message embedding call is performed — see snippet_extraction.py).
    Set to a high value (1.0) so accidental numeric comparisons never trigger.

LOW_CONFIDENCE_THRESHOLD
    Similarity score strictly below this value is flagged as low-confidence.
    Boundary behaviour: similarity == LOW_CONFIDENCE_THRESHOLD → NOT low-confidence.
    Spec: "similarity < 0.40".  Default: 0.40.

SNIPPET_LINE_CAP
    Maximum number of lines included in focused_snippet.
    Default: 8.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Snippet extraction constants
# ---------------------------------------------------------------------------

# Semantic override: how much higher semantic_score must be to beat exact-match.
# Currently unused (semantic scoring is not implemented — no per-message embeddings),
# but placed here so future implementations have a single config location.
SEMANTIC_OVERRIDE_MARGIN: float = 0.25

# Low-confidence threshold.  is_low_confidence = (similarity_score < this value).
# Boundary at exactly 0.40 is NOT low-confidence (strictly less than).
LOW_CONFIDENCE_THRESHOLD: float = 0.40

# Maximum lines in focused_snippet.
SNIPPET_LINE_CAP: int = 8
