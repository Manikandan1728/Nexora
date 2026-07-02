"""
config/retrieval_config.py — Configuration for Phase 5 semantic retrieval.

WHY SEPARATE FROM VectorStoreConfig
------------------------------------
``VectorStoreConfig`` governs *writing* to ChromaDB: collection name,
persist directory, batch size, schema version.  Those concerns are
orthogonal to *reading* from ChromaDB: how many results to return, what
similarity threshold to apply, whether to include metadata in results.

Keeping retrieval configuration separate means:
  • ``VectorStoreConfig`` can evolve independently (e.g. adding write
    batch tuning) without affecting retrieval callers.
  • ``RetrievalConfig`` can be passed to the retrieval pipeline alone,
    without leaking storage-write concerns into retrieval code.
  • Tests can construct a ``RetrievalConfig`` pointing to a ``tmp_path``
    collection without needing to replicate all of ``VectorStoreConfig``.

ENVIRONMENT VARIABLE OVERRIDES
-------------------------------
  NEXORA_COLLECTION_NAME          → collection_name
  NEXORA_PERSIST_DIRECTORY        → persist_directory
  NEXORA_EMBEDDING_MODEL          → embedding_model
  NEXORA_RETRIEVAL_TOP_K          → top_k
  NEXORA_RETRIEVAL_SCORE_THRESHOLD → score_threshold
  NEXORA_DISTANCE_METRIC          → distance_metric
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Defaults — kept in sync with VectorStoreConfig defaults for consistency
# ---------------------------------------------------------------------------
_DEFAULT_COLLECTION_NAME: str = "nexora_knowledge"
_DEFAULT_PERSIST_DIR: str = str(
    Path(__file__).resolve().parent.parent / "data" / "vectors"
)
_DEFAULT_EMBEDDING_MODEL: str = "BAAI/bge-m3"
_DEFAULT_TOP_K: int = 5
_DEFAULT_SCORE_THRESHOLD: float = 0.0
_DEFAULT_DISTANCE_METRIC: str = "cosine"

_VALID_DISTANCE_METRICS: frozenset = frozenset({"cosine", "l2", "ip"})


@dataclass
class RetrievalConfig:
    """
    Configuration for the Phase 5 retrieval pipeline.

    Parameters
    ----------
    collection_name : str
        Name of the ChromaDB collection to query.
        Must match the collection created by Phase 4.
        Default: ``"nexora_knowledge"``.

    persist_directory : str
        Path to the ChromaDB persist directory written by Phase 4.
        Default: ``<project_root>/data/vectors``.

    embedding_model : str
        HuggingFace model identifier used to embed the query.
        Must match the model used to embed the stored documents —
        mixing models produces meaningless similarity scores.
        Default: ``"BAAI/bge-m3"``.

    top_k : int
        Maximum number of results to return from the similarity search.
        The actual number returned may be less if the collection contains
        fewer documents or if ``score_threshold`` filters results out.
        Default: 5.

    score_threshold : float
        Minimum similarity score (in [0, 1]) for a result to be included.
        Results with ``similarity_score < score_threshold`` are dropped.
        Set to 0.0 to return all top_k results regardless of similarity.
        Default: 0.0.

    include_metadata : bool
        Whether to include metadata in query results.
        Default: True.

    include_documents : bool
        Whether to include document text in query results.
        Default: True.

    distance_metric : str
        The distance metric used by the stored collection's HNSW index.
        Used to convert ChromaDB distances to similarity scores:
          • ``"cosine"`` → similarity = 1 - distance  (range [0, 1])
          • ``"l2"``     → similarity = 1 / (1 + distance)
          • ``"ip"``     → similarity = distance (inner product, pre-normalised)
        Must match the metric used when the collection was created.
        Default: ``"cosine"``.

    enable_metadata_filtering : bool
        Whether the ``MetadataFilter`` is active.  When False, any filters
        passed to the pipeline are ignored.
        Default: True.
    """

    collection_name: str = field(
        default_factory=lambda: os.environ.get(
            "NEXORA_COLLECTION_NAME", _DEFAULT_COLLECTION_NAME
        )
    )
    persist_directory: str = field(
        default_factory=lambda: os.environ.get(
            "NEXORA_PERSIST_DIRECTORY", _DEFAULT_PERSIST_DIR
        )
    )
    embedding_model: str = field(
        default_factory=lambda: os.environ.get(
            "NEXORA_EMBEDDING_MODEL", _DEFAULT_EMBEDDING_MODEL
        )
    )
    top_k: int = field(
        default_factory=lambda: int(
            os.environ.get("NEXORA_RETRIEVAL_TOP_K", str(_DEFAULT_TOP_K))
        )
    )
    score_threshold: float = field(
        default_factory=lambda: float(
            os.environ.get(
                "NEXORA_RETRIEVAL_SCORE_THRESHOLD", str(_DEFAULT_SCORE_THRESHOLD)
            )
        )
    )
    include_metadata: bool = True
    include_documents: bool = True
    distance_metric: str = field(
        default_factory=lambda: os.environ.get(
            "NEXORA_DISTANCE_METRIC", _DEFAULT_DISTANCE_METRIC
        )
    )
    enable_metadata_filtering: bool = True

    def __post_init__(self) -> None:
        """Validate all fields immediately after construction."""

        if not self.collection_name or not self.collection_name.strip():
            raise ValueError("RetrievalConfig.collection_name must not be empty.")

        if not self.persist_directory or not self.persist_directory.strip():
            raise ValueError("RetrievalConfig.persist_directory must not be empty.")

        if not self.embedding_model or not self.embedding_model.strip():
            raise ValueError("RetrievalConfig.embedding_model must not be empty.")

        if not isinstance(self.top_k, int) or self.top_k < 1:
            raise ValueError(
                f"RetrievalConfig.top_k must be a positive integer, got {self.top_k!r}."
            )

        if not isinstance(self.score_threshold, (int, float)):
            raise TypeError(
                f"RetrievalConfig.score_threshold must be a float, "
                f"got {type(self.score_threshold).__name__}."
            )
        if not (0.0 <= self.score_threshold <= 1.0):
            raise ValueError(
                f"RetrievalConfig.score_threshold must be in [0.0, 1.0], "
                f"got {self.score_threshold!r}."
            )

        if self.distance_metric not in _VALID_DISTANCE_METRICS:
            raise ValueError(
                f"RetrievalConfig.distance_metric must be one of "
                f"{sorted(_VALID_DISTANCE_METRICS)}, got {self.distance_metric!r}."
            )

    @property
    def persist_path(self) -> Path:
        """Return ``persist_directory`` as a resolved ``pathlib.Path``."""
        return Path(self.persist_directory).resolve()

    def __repr__(self) -> str:
        return (
            f"RetrievalConfig("
            f"collection={self.collection_name!r}, "
            f"top_k={self.top_k}, "
            f"threshold={self.score_threshold}, "
            f"metric={self.distance_metric!r}, "
            f"model={self.embedding_model!r})"
        )
