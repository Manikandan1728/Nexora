"""
app/documents/cleaner.py — Surface-level text cleaner for Phase 2.

WHY THIS MODULE EXISTS
----------------------
Raw WhatsApp messages arrive with platform-specific artefacts:

* Windows-style ``\\r\\n`` line endings mixed with bare ``\\n``
* Invisible Unicode control characters (zero-width spaces, BOM bytes,
  soft hyphens, directional marks) inserted by mobile keyboards
* Runs of three or more blank lines that add no semantic content
* Leading/trailing whitespace on every line

The ``TextCleaner`` class fixes all of these issues **without** altering
the semantic content of any message.  This is a deliberately narrow
responsibility: it does *not* normalise sender names, timestamps, or
punctuation — that is the job of ``TextNormalizer``.

PRINCIPLE
---------
"Do not modify what you do not understand."  The cleaner only removes or
collapses bytes/characters that are guaranteed to be artefacts.  It never
rewrites words, removes punctuation, or changes case.
"""

from __future__ import annotations

import re
import unicodedata


# ---------------------------------------------------------------------------
# Compiled regex patterns — compiled once at import time for performance
# ---------------------------------------------------------------------------

# Invisible / zero-width Unicode categories and specific codepoints
# U+200B ZERO WIDTH SPACE
# U+200C ZERO WIDTH NON-JOINER
# U+200D ZERO WIDTH JOINER
# U+200E LEFT-TO-RIGHT MARK
# U+200F RIGHT-TO-LEFT MARK
# U+2028 LINE SEPARATOR
# U+2029 PARAGRAPH SEPARATOR
# U+FEFF BYTE ORDER MARK / ZERO WIDTH NO-BREAK SPACE
# U+00AD SOFT HYPHEN
_INVISIBLE_UNICODE_RE = re.compile(
    r"[\u00ad\u200b-\u200f\u2028\u2029\ufeff]"
)

# Runs of 3+ consecutive blank lines → collapse to exactly 2 (one empty line)
_EXCESS_BLANK_LINES_RE = re.compile(r"\n{3,}")

# Trailing whitespace on each line (spaces / tabs before line-end or EOF)
_TRAILING_WHITESPACE_RE = re.compile(r"[ \t]+$", re.MULTILINE)

# Leading whitespace on each line (indentation artefacts from export tools)
_LEADING_WHITESPACE_RE = re.compile(r"^[ \t]+", re.MULTILINE)

# Multiple consecutive spaces / tabs within a line → single space
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")


class TextCleaner:
    """
    Stateless utility class that cleans raw message text.

    All methods are pure functions with no side effects.  The class
    exists purely for namespace organisation; every method is a
    ``@staticmethod``.

    Usage
    -----
    ::

        cleaned = TextCleaner.clean("Hello\\r\\n\\nWorld  ")
        # "Hello\\n\\nWorld"
    """

    @staticmethod
    def clean(text: str) -> str:
        """
        Apply the full cleaning pipeline to *text* and return the result.

        Steps (in order):
        1. Normalise line endings  (``\\r\\n`` / ``\\r``  →  ``\\n``)
        2. Remove invisible Unicode characters
        3. Strip trailing whitespace from every line
        4. Strip leading whitespace from every line
        5. Collapse interior multi-space/tab runs to a single space
        6. Collapse excess blank lines (3+ → 2)
        7. Strip leading/trailing whitespace from the whole string

        Args:
            text: Raw message body or assembled chunk text.

        Returns:
            Cleaned text string.  Returns an empty string unchanged.
        """
        if not text:
            return text

        # 1. Normalise line endings
        text = TextCleaner._normalise_line_endings(text)

        # 2. Remove invisible Unicode
        text = TextCleaner._remove_invisible_unicode(text)

        # 3. Strip trailing whitespace per line
        text = _TRAILING_WHITESPACE_RE.sub("", text)

        # 4. Strip leading whitespace per line
        text = _LEADING_WHITESPACE_RE.sub("", text)

        # 5. Collapse interior spaces
        text = _MULTI_SPACE_RE.sub(" ", text)

        # 6. Collapse excess blank lines
        text = _EXCESS_BLANK_LINES_RE.sub("\n\n", text)

        # 7. Strip the whole string
        return text.strip()

    @staticmethod
    def clean_message_body(body: str) -> str:
        """
        Clean an individual message body.

        Identical to ``clean()`` but preserves intentional single blank
        lines within a message (multi-line messages may use them as
        paragraph separators).

        Args:
            body: The ``Message.message`` field value.

        Returns:
            Cleaned message body.
        """
        return TextCleaner.clean(body)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_line_endings(text: str) -> str:
        """Convert all ``\\r\\n`` and bare ``\\r`` to ``\\n``."""
        # Replace Windows CRLF first, then stray CR
        return text.replace("\r\n", "\n").replace("\r", "\n")

    @staticmethod
    def _remove_invisible_unicode(text: str) -> str:
        """Strip zero-width and direction-control Unicode characters."""
        return _INVISIBLE_UNICODE_RE.sub("", text)
