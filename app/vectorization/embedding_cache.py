"""
app/vectorization/embedding_cache.py — In-memory embedding cache for Phase 3.

WHY CACHING MATTERS
--------------------
Embedding is the most expensive operation in the pipeline.  A single
BAAI/bge-m3 forward pass on a modern CPU takes ~50–200 ms per document.
For 100,000 documents that is 83 minutes of pure model inference.

Two sources of redundancy that caching eliminates:

1. **Duplicate documents** — WhatsApp group chats often have the same
   system message (``"Messages are end-to-end encrypted"``) appearing at
   the start of every chat export.  The chunker may also include overlap
   messages in multiple chunks.

2. **Re-runs** — During development, the pipeline is run many times on
   the same export.  Without caching, every run re-embeds everything.

WHY SHA-256
-----------
SHA-256 produces a fixed-length 64-character hex digest for any input
string.  It is:
  • Collision-resistant — two different documents will not hash to the same
    key with any realistic probability.
  • Fast — hashing 100k short documents takes <100ms.
  • Deterministic — the same text always produces the same hash, enabling
    cross-run cache reuse.

WHY MAX_SIZE EVICTION
----------------------
The cache lives in memory.  Without a size cap, a 100k-document corpus
would eventually exhaust RAM (1024 floats × 4 bytes × 100k = ~400 MB for
embeddings alone, plus Python dict overhead).  We evict the oldest entries
(FIFO) when the cap is reached — simple, predictable, and avoids complex
LRU machinery.

THE CACHE IS OPTIONAL
----------------------
The ``EmbeddingPipeline`` accepts ``cache=None`` to disable caching
entirely.  This is the correct behaviour for streaming or one-shot
pipelines where every document is unique and the cache overhead is pure
cost.  Always inject the cache; never assume it is present.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Dict, List, Optional, Tuple

from exceptions.exceptions import CacheError

logger = logging.getLogger(__name__)

# Type alias: cache key → embedding vector
_CacheEntry = List[float]


class EmbeddingCache:
    """
    In-memory LRU-style cache mapping document text hashes to embedding vectors.

    The cache key is a SHA-256 hex digest of the document text (not the
    text itself) to avoid storing large strings twice.

    Parameters
    ----------
    max_size : int
        Maximum number of embeddings to hold in memory.
        When the cache is full, the oldest entry is evicted (FIFO).
        Default: 10,000 (approx. 40 MB for 1024-dim float32 embeddings).

    Usage
    -----
    ::

        cache = EmbeddingCache(max_size=50_000)
        key = cache.compute_key("Hello world")
        hit = cache.get(key)
        if hit is None:
            vector = model.embed_text("Hello world")
            cache.put(key, vector)
    """

    def __init__(self, max_size: int = 10_000) -> None:
        if max_size < 1:
            raise ValueError("EmbeddingCache max_size must be at least 1.")
        self._max_size: int = max_size
        self._store: Dict[str, _CacheEntry] = {}  # insertion-ordered (Python 3.7+)
        self._hits: int = 0
        self._misses: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_key(self, text: str) -> str:
        """
        Compute a deterministic cache key for *text*.

        Uses SHA-256 so that arbitrarily long document texts map to a
        compact 64-character hex string.

        Args:
            text: The document text to hash.

        Returns:
            64-character lowercase hex SHA-256 digest.
        """
        return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()

    def get(self, key: str) -> Optional[_CacheEntry]:
        """
        Retrieve a cached embedding vector by *key*.

        Args:
            key: SHA-256 hex digest produced by ``compute_key()``.

        Returns:
            The cached ``list[float]`` if present, else ``None``.

        Raises:
            CacheError: If a stored entry is unexpectedly malformed.
        """
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None

        if not isinstance(entry, list):
            raise CacheError(
                f"Cache entry for key '{key[:16]}…' is not a list "
                f"(got {type(entry).__name__}).  Cache may be corrupted."
            )

        self._hits += 1
        return entry

    def put(self, key: str, embedding: List[float]) -> None:
        """
        Store an embedding vector under *key*.

        If the cache is at capacity, the oldest entry is evicted before
        the new entry is inserted.

        Args:
            key: SHA-256 hex digest produced by ``compute_key()``.
            embedding: The embedding vector to cache.  Must be non-empty.

        Raises:
            CacheError: If *embedding* is empty or not a list.
        """
        if not isinstance(embedding, list):
            raise CacheError(
                f"Cannot cache non-list type {type(embedding).__name__}.  "
                "Convert to list[float] before calling put()."
            )
        if not embedding:
            raise CacheError("Cannot cache an empty embedding vector.")

        # Evict oldest entry if at capacity
        if len(self._store) >= self._max_size:
            oldest_key = next(iter(self._store))
            del self._store[oldest_key]
            logger.debug(
                "EmbeddingCache: evicted oldest entry (capacity=%d).",
                self._max_size,
            )

        self._store[key] = embedding

    def invalidate(self, key: str) -> bool:
        """
        Remove a specific entry from the cache.

        Args:
            key: SHA-256 hex digest of the text to remove.

        Returns:
            ``True`` if the key was present and removed, ``False`` otherwise.
        """
        if key in self._store:
            del self._store[key]
            return True
        return False

    def clear(self) -> None:
        """Remove all entries and reset hit/miss counters."""
        self._store.clear()
        self._hits = 0
        self._misses = 0
        logger.debug("EmbeddingCache cleared.")

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    @property
    def size(self) -> int:
        """Current number of entries in the cache."""
        return len(self._store)

    @property
    def hits(self) -> int:
        """Cumulative number of cache hits since creation or last ``clear()``."""
        return self._hits

    @property
    def misses(self) -> int:
        """Cumulative number of cache misses since creation or last ``clear()``."""
        return self._misses

    @property
    def hit_rate(self) -> float:
        """
        Cache hit rate as a fraction in [0.0, 1.0].

        Returns 0.0 when no lookups have been made yet.
        """
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def stats(self) -> dict:
        """
        Return a snapshot of cache statistics.

        Returns:
            Dict with keys: ``size``, ``max_size``, ``hits``, ``misses``,
            ``hit_rate``.
        """
        return {
            "size": self.size,
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self.hit_rate, 4),
        }
