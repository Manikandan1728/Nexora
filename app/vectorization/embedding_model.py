"""
app/vectorization/embedding_model.py — BGE-M3 SentenceTransformer wrapper.

WHY BGE-M3 WAS CHOSEN
----------------------
BAAI/bge-m3 is a state-of-the-art multilingual embedding model that:

  • Handles 100+ languages — critical for WhatsApp chats that mix Arabic,
    Chinese, Hindi, English, and emoji in a single message.
  • Produces 1024-dimensional dense vectors — rich enough for semantic
    retrieval, compact enough to store millions of embeddings in RAM.
  • Was trained with contrastive learning on diverse text pairs, making it
    robust to the informal, abbreviated language common in chat exports.
  • Supports sequences up to 8192 tokens, so even after Phase 2 chunking
    at 450 tokens there is ample headroom.
  • Integrates natively with SentenceTransformers, which handles batching,
    pooling (mean-pooling over token embeddings), and normalisation
    internally — eliminating custom inference code.

WHY SENTENCETRANSFORMERS (NOT AUTOMODEL)
-----------------------------------------
``AutoModel.from_pretrained`` + manual mean-pooling + manual normalisation
is ~80 lines of boilerplate that is easy to get wrong (wrong pooling mask,
forgetting to normalise, wrong dtype).  ``SentenceTransformer("BAAI/bge-m3")``
does all of this correctly in one line, with battle-tested production code.

WHY LAZY LOADING
----------------
If the model were loaded at module import time, every test run, every CLI
invocation, and every import of any downstream module would incur a 5–15 s
startup cost and 570 MB of memory allocation.  Lazy loading defers the cost
to the first ``embed_text()`` or ``embed_batch()`` call, so unit tests that
mock the model never pay the loading penalty.

WHY SINGLETON
-------------
Loading the model twice (two ``SentenceTransformer()`` calls) doubles the
GPU/CPU memory footprint.  A singleton ensures the model is shared across
the entire pipeline: ``EmbeddingCache``, ``EmbeddingGenerator``,
``EmbeddingBatcher``, and ``EmbeddingPipeline`` all use the same instance.

WHY normalize_embeddings=True
------------------------------
All returned vectors have L2 norm = 1.  This is required because:
  • Cosine similarity = dot product for unit vectors (faster computation).
  • Vector databases (FAISS, Qdrant, Chroma) are optimised for unit vectors.
  • The EmbeddedDocument model validates that embeddings are normalised.
  • Unnormalised vectors from different documents are not directly comparable.
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional

import numpy as np
from sentence_transformers import SentenceTransformer

from exceptions.exceptions import EmbeddingModelError, EmbeddingGenerationError

logger = logging.getLogger(__name__)

# Default model identifier — the only model used throughout Phase 3.
DEFAULT_MODEL_NAME: str = "BAAI/bge-m3"

# Expected output dimension for BAAI/bge-m3.
# Stored as a constant so downstream code can validate without calling the model.
BGE_M3_EMBEDDING_DIM: int = 1024


class EmbeddingModel:
    """
    Lazy-loading singleton wrapper around ``SentenceTransformer("BAAI/bge-m3")``.

    The underlying ``SentenceTransformer`` is loaded on the first call to
    ``embed_text()`` or ``embed_batch()``, not at instantiation.  This
    design allows the class to be imported, configured, and injected
    into tests without ever touching the model weights.

    Parameters
    ----------
    model_name : str
        HuggingFace model identifier.  Defaults to ``"BAAI/bge-m3"``.
    device : str, optional
        Torch device string (``"cpu"``, ``"cuda"``, ``"mps"``).  When
        ``None``, SentenceTransformers auto-selects the best available
        device.

    Thread Safety
    -------------
    The singleton is not protected by a lock.  Phase 3 is a single-threaded
    batch pipeline.  If future phases parallelise embedding, replace the
    ``_instance`` pattern with a ``threading.Lock``-guarded initialiser.
    """

    _instance: Optional["EmbeddingModel"] = None

    def __new__(
        cls,
        model_name: str = DEFAULT_MODEL_NAME,
        device: Optional[str] = None,
    ) -> "EmbeddingModel":
        """Singleton: reuse the loaded model across all pipeline stages."""
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._initialised = False
            cls._instance = instance
        return cls._instance

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        device: Optional[str] = None,
    ) -> None:
        # Guard: __init__ is called on every access even for a singleton.
        if getattr(self, "_initialised", False):
            return
        self._model_name: str = model_name
        self._device: Optional[str] = device
        self._model: Optional[SentenceTransformer] = None   # lazy-loaded
        self._initialised = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def model_name(self) -> str:
        """The HuggingFace model identifier for this embedding model."""
        return self._model_name

    @property
    def is_loaded(self) -> bool:
        """True after the model weights have been loaded into memory."""
        return self._model is not None

    @property
    def embedding_dim(self) -> int:
        """
        The output embedding dimension.

        Returns the known constant for BGE-M3 before the model is loaded,
        then delegates to the live model for other model names.
        """
        if self._model_name == DEFAULT_MODEL_NAME:
            return BGE_M3_EMBEDDING_DIM
        if self._model is not None:
            return self._model.get_sentence_embedding_dimension()
        return BGE_M3_EMBEDDING_DIM  # fallback for singleton before load

    def embed_text(self, text: str) -> List[float]:
        """
        Embed a single text string and return a normalised float list.

        The model is loaded on the first call (lazy loading).

        Args:
            text: The text string to embed.  Must be non-empty.

        Returns:
            List of ``float`` values with L2 norm ≈ 1.0.
            Length equals ``self.embedding_dim``.

        Raises:
            EmbeddingModelError: If the model cannot be loaded.
            EmbeddingGenerationError: If encoding fails at runtime.
        """
        if not text or not text.strip():
            raise EmbeddingGenerationError(
                "Cannot embed an empty string.  "
                "Ensure documents have non-empty text before calling embed_text()."
            )
        model = self._get_model()
        try:
            vector: np.ndarray = model.encode(
                text,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
            return vector.tolist()
        except Exception as exc:
            raise EmbeddingGenerationError(
                f"Failed to embed text (first 80 chars): {text[:80]!r} — {exc}"
            ) from exc

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a batch of text strings in a single forward pass.

        Batching amortises the GPU kernel launch overhead across many
        documents — for large corpora, ``embed_batch`` is 10–50× faster
        than calling ``embed_text`` in a loop.

        Args:
            texts: List of non-empty text strings.

        Returns:
            List of embedding vectors, same order as ``texts``.
            Each vector is a ``list[float]`` with L2 norm ≈ 1.0.

        Raises:
            EmbeddingModelError: If the model cannot be loaded.
            EmbeddingGenerationError: If batch encoding fails at runtime.
        """
        if not texts:
            return []

        model = self._get_model()
        try:
            start = time.perf_counter()
            matrix: np.ndarray = model.encode(
                texts,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            elapsed = time.perf_counter() - start
            logger.debug(
                "embed_batch: encoded %d texts in %.3fs  (dim=%d)",
                len(texts),
                elapsed,
                matrix.shape[1] if matrix.ndim == 2 else -1,
            )
            return [row.tolist() for row in matrix]
        except Exception as exc:
            raise EmbeddingGenerationError(
                f"Batch embedding failed for {len(texts)} texts: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_model(self) -> SentenceTransformer:
        """
        Return the loaded ``SentenceTransformer``, loading it on first call.

        Raises:
            EmbeddingModelError: If loading fails for any reason.
        """
        if self._model is not None:
            return self._model

        logger.info(
            "Loading SentenceTransformer model '%s'…", self._model_name
        )
        start = time.perf_counter()
        try:
            kwargs: dict = {"normalize_embeddings": False}  # we normalise in encode()
            if self._device:
                kwargs["device"] = self._device
            self._model = SentenceTransformer(self._model_name)
            elapsed = time.perf_counter() - start
            dim = self._model.get_sentence_embedding_dimension()
            logger.info(
                "Model '%s' loaded in %.2fs.  Embedding dim: %d",
                self._model_name,
                elapsed,
                dim,
            )
        except Exception as exc:
            raise EmbeddingModelError(
                f"Failed to load SentenceTransformer model '{self._model_name}': {exc}"
            ) from exc

        return self._model

    @classmethod
    def reset_singleton(cls) -> None:
        """
        Destroy the singleton instance and release model memory.

        Intended for unit tests only — allows injecting a mock model
        without the real weights being loaded.
        """
        if cls._instance is not None:
            cls._instance._model = None
        cls._instance = None
