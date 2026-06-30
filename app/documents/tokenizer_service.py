"""
app/documents/tokenizer_service.py — BGE-M3 tokenizer wrapper for Phase 2.

WHY THIS MODULE EXISTS
----------------------
Chunking strategies that rely on *estimated* token counts (e.g. "1 token ≈
4 characters") produce unreliable chunk boundaries.  A single WhatsApp
message may contain emojis, CJK characters, or mixed-script text where the
character/token ratio varies wildly.

The ``TokenizerService`` loads the *tokenizer only* from ``BAAI/bge-m3``
(the model weights are never touched) and exposes a single responsibility:

    count the exact number of tokens in a string.

WHY CACHE COUNTS
----------------
A 100k-message conversation may trigger hundreds of thousands of
``count_tokens`` calls during chunking (every overlap recalculation calls
count again).  The BGE-M3 tokenizer is fast, but the overhead accumulates.
Caching by string content means identical messages (replies quoting the
same text, system messages repeated across a chat) are tokenized exactly
once.

WHY NOT LOAD THE FULL MODEL
----------------------------
Loading the full embedding model (``AutoModel.from_pretrained``) would
require 570 MB of GPU/CPU memory and add 5-15 seconds of startup latency
per pipeline run.  The tokenizer alone is ~20 MB and loads in under 200 ms.

THREAD SAFETY
-------------
The internal ``_cache`` dict is not protected by a lock.  This is
intentional — Phase 2 is a single-threaded pipeline.  If future phases
parallelise chunking, a ``threading.Lock`` or ``functools.lru_cache``
should be substituted.
"""

from __future__ import annotations

import logging
from typing import Optional

from transformers import AutoTokenizer, PreTrainedTokenizerBase

from exceptions.exceptions import TokenizationError

logger = logging.getLogger(__name__)

# The only model identifier used throughout Phase 2.
BGE_M3_MODEL_ID: str = "BAAI/bge-m3"


class TokenizerService:
    """
    Thin wrapper around the BGE-M3 ``AutoTokenizer``.

    Loads once on first instantiation (or when ``_instance`` is None),
    then reused for every token-count request.

    The class implements a lightweight singleton pattern via a class-level
    ``_instance`` attribute so that the tokenizer is shared across the
    entire pipeline without being passed through every constructor.

    Attributes
    ----------
    _tokenizer : PreTrainedTokenizerBase
        The loaded HuggingFace tokenizer.
    _cache : dict[str, int]
        LRU-style dict mapping ``text → token_count``.
        Bounded by ``max_cache_size`` to prevent unbounded memory growth
        in very large conversations.
    """

    _instance: Optional["TokenizerService"] = None

    def __new__(cls, max_cache_size: int = 50_000) -> "TokenizerService":
        """Singleton: reuse the loaded tokenizer across pipeline stages."""
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._initialised = False
            cls._instance = instance
        return cls._instance

    def __init__(self, max_cache_size: int = 50_000) -> None:
        # __init__ is called every time even for the singleton; guard with flag.
        if getattr(self, "_initialised", False):
            return

        logger.info("Loading BGE-M3 tokenizer from '%s'…", BGE_M3_MODEL_ID)
        try:
            self._tokenizer: PreTrainedTokenizerBase = (
                AutoTokenizer.from_pretrained(BGE_M3_MODEL_ID)
            )
        except Exception as exc:
            raise TokenizationError(
                f"Failed to load tokenizer '{BGE_M3_MODEL_ID}': {exc}"
            ) from exc

        self._cache: dict[str, int] = {}
        self._max_cache_size: int = max_cache_size
        self._initialised = True
        logger.info(
            "BGE-M3 tokenizer loaded.  Vocab size: %d",
            self._tokenizer.vocab_size,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def count_tokens(self, text: str) -> int:
        """
        Return the exact BGE-M3 token count for *text*.

        Results are cached by ``text`` content.  The cache is evicted when
        it reaches ``max_cache_size`` (oldest entries are dropped first).

        Args:
            text: Any string — message body, assembled chunk, or a
                  single sentence fragment.

        Returns:
            Number of tokens as a non-negative integer.  An empty string
            returns 0.

        Raises:
            TokenizationError: If the tokenizer raises an unexpected error.
        """
        if not text:
            return 0

        cached = self._cache.get(text)
        if cached is not None:
            return cached

        try:
            token_ids: list[int] = self._tokenizer.encode(
                text,
                add_special_tokens=False,
            )
            count = len(token_ids)
        except Exception as exc:
            raise TokenizationError(
                f"Tokenization failed for text (first 80 chars): "
                f"{text[:80]!r} — {exc}"
            ) from exc

        # Evict oldest entries when cache is full
        if len(self._cache) >= self._max_cache_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        self._cache[text] = count
        return count

    def count_tokens_batch(self, texts: list[str]) -> list[int]:
        """
        Count tokens for a list of strings, using the cache for any
        previously seen strings.

        This is more efficient than calling ``count_tokens`` in a loop
        because uncached texts are tokenized in a single batch call.

        Args:
            texts: List of strings to tokenize.

        Returns:
            List of integer token counts, same order as input.
        """
        if not texts:
            return []

        counts: list[int] = [0] * len(texts)
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        for i, text in enumerate(texts):
            if not text:
                counts[i] = 0
            elif text in self._cache:
                counts[i] = self._cache[text]
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        if uncached_texts:
            try:
                encoded = self._tokenizer(
                    uncached_texts,
                    add_special_tokens=False,
                    return_attention_mask=False,
                    return_token_type_ids=False,
                )
                for idx, text, token_ids in zip(
                    uncached_indices, uncached_texts, encoded["input_ids"]
                ):
                    count = len(token_ids)
                    counts[idx] = count
                    # Cache with eviction
                    if len(self._cache) >= self._max_cache_size:
                        oldest_key = next(iter(self._cache))
                        del self._cache[oldest_key]
                    self._cache[text] = count
            except Exception as exc:
                raise TokenizationError(
                    f"Batch tokenization failed: {exc}"
                ) from exc

        return counts

    @property
    def cache_size(self) -> int:
        """Current number of entries in the token-count cache."""
        return len(self._cache)

    def clear_cache(self) -> None:
        """Flush the token-count cache.  Useful between pipeline runs in tests."""
        self._cache.clear()

    @classmethod
    def reset_singleton(cls) -> None:
        """
        Destroy the singleton instance.

        Intended for use in unit tests only — allows creating a fresh
        instance (e.g. with a smaller ``max_cache_size``) between test runs.
        """
        cls._instance = None
