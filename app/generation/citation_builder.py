"""
app/generation/citation_builder.py — Builds structured citations from
retrieved documents.

WHY CITATIONS IMPROVE TRUST
----------------------------
A plain LLM answer is unverifiable. The user cannot tell whether the
model invented "You shared a PDF on March 5th" or whether it actually
appears in the knowledge base. Citations close this gap: each Citation
object records the exact document chunk that was included in the prompt,
so the caller can independently verify the claim.

WHY CITATIONS ARE BUILT HERE, NOT BY THE LLM
---------------------------------------------
Asking the LLM to generate its own citations introduces the same
hallucination risk we are trying to prevent: the model may fabricate
plausible-looking document IDs, timestamps, or source names. Building
citations directly from the ``RetrievedDocument`` objects means they are
100% grounded in the actual retrieval results — the LLM is never
consulted.

WHY RANK ORDER IS PRESERVED
----------------------------
Citations are ordered by retrieval rank so the consumer (a future API,
UI, or CLI) can display them in the same order as the LLM saw the
context. Rank 1 = most semantically similar = most likely to have driven
the answer.

SAFE FALLBACKS
--------------
Metadata fields such as ``source_chat``, ``chunk_index``, and timestamps
come from ChromaDB metadata written by Phase 4. In edge cases (very old
exports, schema changes, or partially populated metadata) these fields
may be absent. The builder falls back to safe defaults rather than
raising on every missing field — CitationError is reserved for contract
violations (wrong input type), not for optional metadata gaps.
"""

from __future__ import annotations

import logging
from typing import List

from models.retrieved_document import RetrievedDocument
from models.answer import Citation
from exceptions.exceptions import CitationError

logger = logging.getLogger(__name__)


class CitationBuilder:
    """
    Builds an immutable tuple of ``Citation`` objects from a list of
    ``RetrievedDocument`` objects.

    This class is stateless — all logic lives in the single ``build``
    method.  It exists as a class (not a module-level function) to be
    consistent with the rest of the generation package and to allow
    future subclassing for specialised citation formats.

    No LLM calls are made.  No external I/O is performed.
    """

    def build(self, documents: List[RetrievedDocument]) -> tuple:
        """
        Build and return a tuple of ``Citation`` objects.

        Citations are produced in the same order as *documents*, which is
        retrieval rank order (rank 1 first).  One Citation is created per
        document; no de-duplication is performed.

        Args:
            documents: Non-empty list of ``RetrievedDocument`` objects
                       from Phase 5 retrieval.

        Returns:
            Immutable ``tuple[Citation, ...]``, one per document.

        Raises:
            CitationError: If *documents* is not a list, is empty, or
                           contains non-``RetrievedDocument`` items.
        """
        self._validate(documents)

        citations: List[Citation] = []
        for doc in documents:
            citations.append(self._build_one(doc))

        result = tuple(citations)
        logger.debug(
            "CitationBuilder: built %d citation(s).", len(result)
        )
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_one(doc: RetrievedDocument) -> Citation:
        """
        Build a single ``Citation`` from one ``RetrievedDocument``.

        Metadata fields are read with safe fallbacks so that gaps in
        ChromaDB metadata never crash citation building.

        Args:
            doc: A single ``RetrievedDocument``.

        Returns:
            A populated ``Citation`` instance.
        """
        meta = doc.metadata

        source_chat: str = str(
            meta.get("source_chat", "") or ""
        ).strip() or "Unknown"

        raw_chunk = meta.get("chunk_index", 0)
        try:
            chunk_index = int(raw_chunk)
            if chunk_index < 0:
                chunk_index = 0
        except (TypeError, ValueError):
            chunk_index = 0

        start_timestamp: str = str(
            meta.get("start_timestamp", "") or ""
        ).strip()

        end_timestamp: str = str(
            meta.get("end_timestamp", "") or ""
        ).strip()

        return Citation(
            document_id=doc.document_id,
            similarity_score=doc.similarity_score,
            source_chat=source_chat,
            chunk_index=chunk_index,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            rank=doc.rank,
        )

    @staticmethod
    def _validate(documents: List[RetrievedDocument]) -> None:
        """
        Validate the input list before building citations.

        Raises:
            CitationError: On any contract violation.
        """
        if not isinstance(documents, list):
            raise CitationError(
                f"CitationBuilder.build() expects a list, "
                f"got {type(documents).__name__}."
            )
        if len(documents) == 0:
            raise CitationError(
                "CitationBuilder received an empty document list.  "
                "Pass at least one RetrievedDocument."
            )
        for i, doc in enumerate(documents):
            if not isinstance(doc, RetrievedDocument):
                raise CitationError(
                    f"Item at index {i} is not a RetrievedDocument "
                    f"(got {type(doc).__name__}).  "
                    f"Only Phase 5 retrieval results may be passed to CitationBuilder."
                )
