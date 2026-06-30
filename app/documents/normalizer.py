"""
app/documents/normalizer.py — Semantic-preserving text normaliser for Phase 2.

WHY THIS MODULE EXISTS
----------------------
Embedding models are sensitive to surface variation.  Two messages that
mean the same thing but differ only in Unicode normalisation form, sender
name casing, or quote character style will produce slightly different
embedding vectors.  Normalising these variations *before* embedding
improves recall consistency and reduces the vocabulary the model must
bridge.

Responsibilities
----------------
1. **Sender-name normalisation** — strip excess whitespace from names;
   title-case them consistently so "alice", "Alice ", and " alice" all
   become "Alice".
2. **Unicode NFC normalisation** — decomposed accented characters
   (e.g. ``e`` + combining accent) are composed into their canonical
   precomposed forms.  This fixes sorting, search, and tokenizer
   boundary issues without losing any characters.
3. **Timestamp string normalisation** — not parsed to ``datetime``; only
   surface-level whitespace is trimmed so downstream consumers get a
   predictable string format.
4. **Punctuation normalisation** — curly quotes, em-dashes, and
   ellipsis characters are mapped to their ASCII equivalents so the
   tokenizer does not split them into rare sub-word tokens.

PRINCIPLE
---------
"Reduce surface noise; preserve meaning."  Nothing is deleted.  Every
transformation is reversible in principle.
"""

from __future__ import annotations

import re
import unicodedata


# ---------------------------------------------------------------------------
# Punctuation normalisation map — applied character-by-character
# ---------------------------------------------------------------------------
_PUNCT_MAP: dict[str, str] = {
    "\u2018": "'",   # LEFT SINGLE QUOTATION MARK
    "\u2019": "'",   # RIGHT SINGLE QUOTATION MARK
    "\u201c": '"',   # LEFT DOUBLE QUOTATION MARK
    "\u201d": '"',   # RIGHT DOUBLE QUOTATION MARK
    "\u2013": "-",   # EN DASH
    "\u2014": "--",  # EM DASH
    "\u2026": "...", # HORIZONTAL ELLIPSIS
    "\u00b7": ".",   # MIDDLE DOT
    "\u2022": "-",   # BULLET
    "\u2032": "'",   # PRIME (foot mark used as apostrophe)
    "\u2033": '"',   # DOUBLE PRIME
}

# Build a compiled regex that matches any key in the map
_PUNCT_RE = re.compile(
    "|".join(re.escape(k) for k in _PUNCT_MAP)
)

# Multiple spaces within a line → single space (post-normalisation clean-up)
_MULTI_SPACE_RE = re.compile(r" {2,}")


class TextNormalizer:
    """
    Stateless text normaliser.

    All methods are pure functions (``@staticmethod``).

    Usage
    -----
    ::

        name = TextNormalizer.normalize_sender_name("  alice  ")
        # "Alice"

        text = TextNormalizer.normalize_text("Hello\\u2019s world\\u2026")
        # "Hello's world..."
    """

    @staticmethod
    def normalize_sender_name(name: str) -> str:
        """
        Normalise a WhatsApp sender display name.

        Steps:
        1. Strip surrounding whitespace.
        2. Apply Unicode NFC normalisation (compose combining characters).
        3. Title-case the result so names are consistent regardless of
           how they were saved on the exporting device.

        Args:
            name: Raw sender name from ``Message.sender``.

        Returns:
            Normalised display name.  Returns the input unchanged if it
            is empty or ``"SYSTEM"``.
        """
        if not name or name == "SYSTEM":
            return name
        normalised = unicodedata.normalize("NFC", name.strip())
        return normalised.title()

    @staticmethod
    def normalize_timestamp(timestamp: str) -> str:
        """
        Light normalisation for a timestamp string.

        Only trims surrounding whitespace and collapses interior runs of
        spaces.  The timestamp is never parsed here — ``DateTimeUtils``
        handles parsing.

        Args:
            timestamp: Raw ``Message.timestamp`` string.

        Returns:
            Whitespace-trimmed timestamp string.
        """
        if not timestamp:
            return timestamp
        return _MULTI_SPACE_RE.sub(" ", timestamp.strip())

    @staticmethod
    def normalize_text(text: str) -> str:
        """
        Normalise arbitrary text for embedding readiness.

        Steps:
        1. Unicode NFC normalisation.
        2. Map typographic punctuation to ASCII equivalents.
        3. Collapse any double-spaces introduced by substitution.

        Args:
            text: Cleaned message body or assembled chunk text.

        Returns:
            Normalised text string.  Returns empty string unchanged.
        """
        if not text:
            return text

        # 1. NFC
        text = unicodedata.normalize("NFC", text)

        # 2. Punctuation map
        text = _PUNCT_RE.sub(lambda m: _PUNCT_MAP[m.group(0)], text)

        # 3. Collapse double-spaces
        text = _MULTI_SPACE_RE.sub(" ", text)

        return text

    @staticmethod
    def normalize_participants(participants: list[str]) -> list[str]:
        """
        Apply ``normalize_sender_name`` to every participant name and
        return a new sorted list with duplicates removed.

        Args:
            participants: List of raw participant names.

        Returns:
            Sorted, deduplicated list of normalised names.
        """
        seen: set[str] = set()
        result: list[str] = []
        for name in participants:
            normalised = TextNormalizer.normalize_sender_name(name)
            if normalised not in seen:
                seen.add(normalised)
                result.append(normalised)
        return sorted(result)
