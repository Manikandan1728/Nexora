"""
api/schemas/request_models.py — Pydantic v2 request models for Phase 7.

All field validators enforce business rules so that route handlers never
need to re-validate their inputs.  Invalid input raises ``RequestValidationError``
which is mapped to ``400`` by the FastAPI default handler (supplemented by
our centralised ``error_handlers.py``).
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Collection name safety
# ---------------------------------------------------------------------------

# ChromaDB requires: 3-512 chars, alphanumerics / dots / hyphens / underscores,
# start and end with alphanumeric.  We enforce a strict subset.
_COLLECTION_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._\-]{1,510}[a-zA-Z0-9]$")

# Path-traversal / injection patterns — always reject these
_UNSAFE_PATH_RE = re.compile(r"[/\\]|\.\.")


def _validate_collection_name(v: str) -> str:
    """
    Validate that *v* is a safe, well-formed collection name.

    Raises:
        ValueError: If the name contains path separators, ``..``,
                    or does not match the allowed pattern.
    """
    if not v or not v.strip():
        raise ValueError("collection_name must not be empty.")
    if _UNSAFE_PATH_RE.search(v):
        raise ValueError(
            "collection_name must not contain path separators or '..'."
        )
    if not _COLLECTION_NAME_RE.match(v):
        raise ValueError(
            "collection_name must be 3-512 chars, start and end with "
            "alphanumeric, and contain only alphanumerics, dots, hyphens, "
            "or underscores."
        )
    return v


# ---------------------------------------------------------------------------
# Query request
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    """
    Request body for ``POST /query``.

    Attributes
    ----------
    question : str
        The user's natural-language question.  Must be non-empty and at
        most 2000 characters.

    collection_name : str
        Name of the ChromaDB collection to query.  Must be a safe,
        well-formed identifier — path traversal characters are rejected.

    top_k : int
        Maximum number of retrieved documents to return.
        Bounded to ``[1, 50]``.

    filters : dict | None
        Optional metadata filter dict forwarded to Phase 5.
        Keys must be strings; values must be scalar or operator-dict types
        supported by ``MetadataFilter``.

    use_rag : bool
        When ``True``, Phase 6 RAG generation is attempted after retrieval.
        When ``False``, retrieval-only results are returned.
    """

    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The natural-language question to answer.",
    )
    collection_name: str = Field(
        ...,
        description="Name of an existing ChromaDB collection.",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum number of retrieved documents (1–50).",
    )
    filters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional metadata filter dict forwarded to Phase 5.",
    )
    use_rag: bool = Field(
        default=True,
        description="Whether to run Phase 6 RAG after retrieval.",
    )

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, v: str) -> str:
        """Reject whitespace-only questions."""
        if not v.strip():
            raise ValueError("question must not be empty or whitespace-only.")
        return v

    @field_validator("collection_name")
    @classmethod
    def collection_name_safe(cls, v: str) -> str:
        """Delegate to shared collection-name validator."""
        return _validate_collection_name(v)
