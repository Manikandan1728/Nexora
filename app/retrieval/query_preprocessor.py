"""
app/retrieval/query_preprocessor.py — Query text cleaning and validation.

WHY THIS MODULE EXISTS
----------------------
Raw user queries arrive with surface noise that degrades retrieval quality:

  • Leading/trailing whitespace from copy-paste or form input
  • Multiple consecutive spaces from poor IME or autocorrect output
  • Decomposed Unicode (e.g. "cafe\u0301" instead of "café") that may
    tokenize differently from the composed form used in stored documents
  • Completely empty strings that would crash the embedding model

The preprocessor is a narrow, deterministic gate — it either returns a
clean query string or raises ``QueryValidationError``.  It never modifies
semantic content: it does not translate, stem, remove stopwords, expand
abbreviations, or rewrite the query in any way.

PRINCIPLE
---------
"Minimal intervention, maximum safety."  The embedding model handles
semantic understanding — the preprocessor only removes noise that prevents
the query from reaching the model correctly.
"""

from __future__ import annotations

import re
import unicodedata

from exceptions.exceptions import QueryValidationError

# Compiled once at import time for performance
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
_NEWLINE_RE = re.compile(r"[\r\n]+")


class QueryPreprocessor:
    """
    Stateless query preprocessor.

    All methods are pure functions (``@staticmethod``).  The class exists
    purely as a namespace; no state is held between calls.

    Usage
    -----
    ::

        cleaned = QueryPreprocessor.preprocess("  What did Alice say?  ")
        # "What did Alice say?"
    """

    @staticmethod
    def preprocess(query: str) -> str:
        """
        Validate and clean a raw query string.

        Steps (in order):
        1. Type-check — must be a str.
        2. Unicode NFC normalisation — compose decomposed characters.
        3. Normalise newlines — collapse ``\\r\\n`` / ``\\r`` / ``\\n`` to a space.
        4. Strip surrounding whitespace.
        5. Collapse interior runs of spaces/tabs to a single space.
        6. Reject empty or whitespace-only queries.

        Args:
            query: Raw query string from the user.

        Returns:
            Clean, non-empty query string.

        Raises:
            QueryValidationError: If the query is not a string, is empty,
                                  or contains only whitespace after cleaning.
        """
        if not isinstance(query, str):
            raise QueryValidationError(
                f"Query must be a string, got {type(query).__name__}."
            )

        # 1. NFC normalisation — ensures consistent Unicode representation
        query = unicodedata.normalize("NFC", query)

        # 2. Normalise newlines → single space
        query = _NEWLINE_RE.sub(" ", query)

        # 3. Strip surrounding whitespace
        query = query.strip()

        # 4. Collapse interior multi-space/tab runs
        query = _MULTI_SPACE_RE.sub(" ", query)

        # 5. Reject empty result
        if not query:
            raise QueryValidationError(
                "Query must not be empty or contain only whitespace."
            )

        return query

    @staticmethod
    def is_valid(query: str) -> bool:
        """
        Return True when ``preprocess(query)`` would succeed without raising.

        Useful for fast pre-flight checks without exception handling overhead.

        Args:
            query: Raw query string.

        Returns:
            True if the query is processable, False otherwise.
        """
        try:
            QueryPreprocessor.preprocess(query)
            return True
        except QueryValidationError:
            return False
