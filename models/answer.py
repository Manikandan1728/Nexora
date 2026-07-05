"""
models/answer.py — Immutable grounded answer model for Phase 6.

WHY RAG PRODUCES A GroundedAnswer, NOT A PLAIN STRING
------------------------------------------------------
A raw LLM completion string carries no provenance information. Callers
cannot tell:
  - Which retrieved documents supported the answer.
  - How confident the system is (based on retrieval scores).
  - Which model and provider generated it.
  - How long generation took (for SLA monitoring).
  - How many tokens were consumed (for cost tracking).

``GroundedAnswer`` bundles all of this alongside the answer text so that
every consumer — a CLI, an API endpoint, a logging system — has everything
it needs without making additional calls.

WHY FROZEN
----------
Answers are write-once outputs of the generation pipeline. Allowing
mutation after construction would make it impossible to cache or deduplicate
them safely. ``frozen=True`` also makes instances hashable and safe to
use in sets and as dict keys.

CITATIONS vs ANSWER TEXT
-------------------------
The answer text is the human-readable response. Citations are structured
provenance records linking claims back to specific retrieved chunks. They
are kept separate so downstream systems (future API, UI) can render them
independently — e.g. showing footnote numbers inline or displaying a
separate "sources" panel.

CONFIDENCE
----------
Confidence is derived from the mean similarity score of the top-k retrieved
documents used to build the context. It is NOT the model's own confidence
estimate (which is unreliable for factual claims). This makes it a
retrieval-grounded signal: high confidence = the knowledge base strongly
matched the query.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class Citation:
    """
    A single provenance record linking the answer to a retrieved chunk.

    Attributes
    ----------
    document_id : str
        The ``RetrievedDocument.document_id`` this citation refers to.

    similarity_score : float
        The retrieval similarity score in [0.0, 1.0].

    source_chat : str
        The ``source_chat`` metadata field from the retrieved document.
        Tells the user which conversation this chunk came from.

    chunk_index : int
        Zero-based chunk position within the source chat.

    start_timestamp : str
        Timestamp of the first message in this chunk (empty if unavailable).

    end_timestamp : str
        Timestamp of the last message in this chunk (empty if unavailable).

    rank : int
        The retrieval rank (1-based) of this document.
    """

    document_id: str
    similarity_score: float
    source_chat: str
    chunk_index: int
    start_timestamp: str
    end_timestamp: str
    rank: int

    def __post_init__(self) -> None:
        if not isinstance(self.document_id, str) or not self.document_id.strip():
            raise ValueError("Citation.document_id must be a non-empty string.")
        if not (0.0 <= self.similarity_score <= 1.0):
            raise ValueError(
                f"Citation.similarity_score must be in [0.0, 1.0], "
                f"got {self.similarity_score!r}."
            )
        if not isinstance(self.rank, int) or self.rank < 1:
            raise ValueError(
                f"Citation.rank must be a positive integer, got {self.rank!r}."
            )
        if not isinstance(self.chunk_index, int) or self.chunk_index < 0:
            raise ValueError(
                f"Citation.chunk_index must be >= 0, got {self.chunk_index!r}."
            )

    def __repr__(self) -> str:
        return (
            f"Citation(rank={self.rank}, score={self.similarity_score:.4f}, "
            f"chat={self.source_chat!r}, chunk={self.chunk_index})"
        )


@dataclass(frozen=True)
class GroundedAnswer:
    """
    The complete output of Phase 6 — a grounded, cited LLM answer.

    Attributes
    ----------
    question : str
        The original user question (post-preprocessing).

    answer : str
        The LLM-generated answer, grounded in retrieved context.
        May be the fallback "I could not find that information in your
        knowledge base." when context is insufficient.

    citations : tuple[Citation, ...]
        Ordered tuple of citations, one per retrieved document used.
        Immutable so ``GroundedAnswer`` can be hashed.

    confidence : float
        Mean similarity score of the retrieved documents used for context.
        In [0.0, 1.0].  Higher = knowledge base strongly matched the query.

    provider : str
        LLM provider name (``"openai"`` or ``"ollama"``).

    model : str
        Exact model identifier used for generation.

    generation_time : float
        Wall-clock seconds from prompt submission to completion receipt.

    tokens_used : int
        Total tokens consumed (prompt + completion) if the provider
        reported this; 0 otherwise.
    """

    question: str
    answer: str
    citations: tuple
    confidence: float
    provider: str
    model: str
    generation_time: float
    tokens_used: int

    def __post_init__(self) -> None:
        if not isinstance(self.question, str):
            raise TypeError("GroundedAnswer.question must be a str.")
        if not isinstance(self.answer, str):
            raise TypeError("GroundedAnswer.answer must be a str.")
        if not isinstance(self.citations, tuple):
            raise TypeError("GroundedAnswer.citations must be a tuple.")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"GroundedAnswer.confidence must be in [0.0, 1.0], "
                f"got {self.confidence!r}."
            )
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise ValueError("GroundedAnswer.provider must be a non-empty string.")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("GroundedAnswer.model must be a non-empty string.")
        if self.generation_time < 0:
            raise ValueError(
                f"GroundedAnswer.generation_time must be >= 0, "
                f"got {self.generation_time!r}."
            )
        if not isinstance(self.tokens_used, int) or self.tokens_used < 0:
            raise ValueError(
                f"GroundedAnswer.tokens_used must be a non-negative integer, "
                f"got {self.tokens_used!r}."
            )

    @property
    def has_citations(self) -> bool:
        """True when at least one citation is present."""
        return len(self.citations) > 0

    @property
    def citation_count(self) -> int:
        """Number of citations supporting this answer."""
        return len(self.citations)

    def __repr__(self) -> str:
        return (
            f"GroundedAnswer("
            f"provider={self.provider!r}, model={self.model!r}, "
            f"confidence={self.confidence:.4f}, "
            f"citations={self.citation_count}, "
            f"time={self.generation_time:.2f}s, "
            f"tokens={self.tokens_used})"
        )
