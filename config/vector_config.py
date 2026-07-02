"""
config/vector_config.py — Configuration for Phase 4 vector storage.

WHY THIS MODULE EXISTS
----------------------
Hard-coding collection names, directory paths, and distance metrics
throughout the storage layer creates brittle code that is impossible
to test in isolation.  A single, validated configuration object:

  • Makes every tunable parameter visible in one place.
  • Allows environment-variable overrides so the same code runs in
    development (temp directory), CI (in-memory), and production
    (persistent path) without code changes.
  • Enables dependency injection — tests pass a config pointing to a
    temporary directory; production passes a config pointing to the
    real data/vectors path.
  • Captures schema versioning so future model upgrades can detect
    and reject stale collections.

ENVIRONMENT VARIABLE OVERRIDES
-------------------------------
All fields can be overridden by environment variables:

  NEXORA_COLLECTION_NAME       → collection_name
  NEXORA_PERSIST_DIRECTORY     → persist_directory
  NEXORA_DISTANCE_METRIC       → distance_metric  (cosine | l2 | ip)
  NEXORA_STORAGE_BATCH_SIZE    → batch_size
  NEXORA_EMBEDDING_MODEL       → embedding_model
  NEXORA_SCHEMA_VERSION        → schema_version

This follows the twelve-factor app principle: configuration comes from
the environment, not from the source tree.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
_DEFAULT_COLLECTION_NAME: str = "nexora_knowledge"
_DEFAULT_PERSIST_DIR: str = str(
    Path(__file__).resolve().parent.parent / "data" / "vectors"
)
_DEFAULT_DISTANCE_METRIC: str = "cosine"
_DEFAULT_BATCH_SIZE: int = 100
_DEFAULT_EMBEDDING_MODEL: str = "BAAI/bge-m3"
_DEFAULT_SCHEMA_VERSION: str = "1.0.0"

# Supported ChromaDB distance metrics
_VALID_DISTANCE_METRICS: frozenset = frozenset({"cosine", "l2", "ip"})


@dataclass
class VectorStoreConfig:
    """
    Immutable-by-convention configuration for the ChromaDB vector store.

    Parameters
    ----------
    collection_name : str
        Name of the ChromaDB collection.  Must be a non-empty string
        containing only alphanumerics, hyphens, and underscores.
        Default: ``"nexora_knowledge"``.

    persist_directory : str
        Absolute or relative path where ChromaDB will write its on-disk
        SQLite database and index files.
        Default: ``<project_root>/data/vectors``.

    distance_metric : str
        Distance function used by the HNSW index inside ChromaDB.
        Must be one of ``"cosine"``, ``"l2"``, or ``"ip"``.
        Use ``"cosine"`` for normalised BGE-M3 embeddings.
        Default: ``"cosine"``.

    batch_size : int
        Number of ``EmbeddedDocument`` objects inserted per ChromaDB
        ``collection.add()`` call.  Larger batches reduce round-trip
        overhead; smaller batches reduce peak memory usage.
        Default: 100.

    embedding_model : str
        Full HuggingFace model identifier that produced the embeddings
        being stored.  Recorded in collection metadata for schema
        validation — a mismatch between stored and incoming models
        raises ``CollectionError``.
        Default: ``"BAAI/bge-m3"``.

    schema_version : str
        Semantic version string for the storage schema.  Increment this
        when the metadata structure changes incompatibly so that existing
        collections can be detected and migrated or rejected.
        Default: ``"1.0.0"``.
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
    distance_metric: str = field(
        default_factory=lambda: os.environ.get(
            "NEXORA_DISTANCE_METRIC", _DEFAULT_DISTANCE_METRIC
        )
    )
    batch_size: int = field(
        default_factory=lambda: int(
            os.environ.get("NEXORA_STORAGE_BATCH_SIZE", str(_DEFAULT_BATCH_SIZE))
        )
    )
    embedding_model: str = field(
        default_factory=lambda: os.environ.get(
            "NEXORA_EMBEDDING_MODEL", _DEFAULT_EMBEDDING_MODEL
        )
    )
    schema_version: str = field(
        default_factory=lambda: os.environ.get(
            "NEXORA_SCHEMA_VERSION", _DEFAULT_SCHEMA_VERSION
        )
    )

    def __post_init__(self) -> None:
        """Validate all fields immediately after construction."""

        # collection_name
        if not self.collection_name or not self.collection_name.strip():
            raise ValueError("VectorStoreConfig.collection_name must not be empty.")

        # persist_directory — must be a non-empty string (existence checked later)
        if not self.persist_directory or not self.persist_directory.strip():
            raise ValueError("VectorStoreConfig.persist_directory must not be empty.")

        # distance_metric
        if self.distance_metric not in _VALID_DISTANCE_METRICS:
            raise ValueError(
                f"VectorStoreConfig.distance_metric must be one of "
                f"{sorted(_VALID_DISTANCE_METRICS)}, got {self.distance_metric!r}."
            )

        # batch_size
        if not isinstance(self.batch_size, int) or self.batch_size < 1:
            raise ValueError(
                f"VectorStoreConfig.batch_size must be a positive integer, "
                f"got {self.batch_size!r}."
            )

        # embedding_model
        if not self.embedding_model or not self.embedding_model.strip():
            raise ValueError("VectorStoreConfig.embedding_model must not be empty.")

        # schema_version
        if not self.schema_version or not self.schema_version.strip():
            raise ValueError("VectorStoreConfig.schema_version must not be empty.")

    @property
    def persist_path(self) -> Path:
        """Return ``persist_directory`` as a resolved ``pathlib.Path``."""
        return Path(self.persist_directory).resolve()

    def __repr__(self) -> str:
        return (
            f"VectorStoreConfig("
            f"collection={self.collection_name!r}, "
            f"persist={self.persist_directory!r}, "
            f"metric={self.distance_metric!r}, "
            f"batch_size={self.batch_size}, "
            f"model={self.embedding_model!r}, "
            f"schema={self.schema_version!r})"
        )
