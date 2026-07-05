"""
app/generation/context_builder.py — Formats retrieved documents into a
context string for the LLM prompt.

WHY CONTEXT BUILDING IS A SEPARATE STEP
----------------------------------------
The LLM does not receive Python objects — it receives a single text
string. The context builder is the boundary layer that converts the
structured ``List[RetrievedDocument]`` from Phase 5 into that string.

By isolating this concern in its own class:
  * The PromptBuilder stays focused on prompt structure, not data formatting.
  * The context format can be changed (e.g. adding JSON metadata, switching
    separators) without touching any other generation component.
  * The token budget is enforced in one place — the PromptBuilder never
    needs to worry about context length.

WHY RANK ORDER IS PRESERVED
----------------------------
Phase 5 orders results by descending similarity score. The LLM should
see the most relevant document first, because studies show that LLMs
weight earlier tokens more heavily when generating. Reordering would
corrupt the semantic signal that Phase 5 worked to produce.

WHY A CHARACTER-BASED TOKEN BUDGET
------------------------------------
The precise token count for a context string requires running the LLM's
tokenizer, which would couple Phase 6 to the BGE-M3 tokenizer (Phase 2/3)
or to each LLM's own tokenizer. A conservative character-based estimate
(4 chars per token) is safe, fast, and avoids adding dependencies. It
will always truncate before the true token limit, never after — this is
the correct direction for the error.

WHY NEVER MUTATE RetrievedDocument
------------------------------------
``RetrievedDocument`` is a frozen dataclass. Even if mutation were
possible, modifying a retrieval result to build a prompt would violate
the single-responsibility principle: retrieval results are data, not
mutable working state.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from models.retrieved_document import RetrievedDocument
from config.llm_config import LLMConfig
from exceptions.exceptions import ContextBuildError

logger = logging.getLogger(__name__)

# Conservative chars-per-token estimate (always errs towards fewer tokens)
_CHARS_PER_TOKEN: int = 4

# Separator drawn between documents in the context block
_DOC_SEPARATOR: str = "\n" + "-" * 40 + "\n"


class ContextBuilder:
    """
    Converts a ranked list of ``RetrievedDocument`` objects into a single
    context string suitable for insertion into an LLM prompt.

    Parameters
    ----------
    config : LLMConfig
        Configuration providing ``context_token_budget`` — the maximum
        number of tokens the context string may consume.

    Design contract
    ---------------
    * Documents are included in the exact order they are supplied (rank
      order from Phase 5 — descending similarity).
    * Each document block includes: rank, similarity score, document ID,
      source chat, timestamp window, chunk index, and text.
    * Documents are added greedily until the next document would exceed
      the character budget.  The last document that fits is included in
      full; there is no partial truncation of document text.
    * If no document fits within the budget, ``ContextBuildError`` is
      raised rather than silently returning an empty context — an empty
      context would cause the LLM to hallucinate with no grounding.
    """

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        # Convert token budget to a character budget with conservative ratio
        self._char_budget: int = config.context_token_budget * _CHARS_PER_TOKEN

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, documents: List[RetrievedDocument]) -> str:
        """
        Build and return the context string from *documents*.

        Args:
            documents: Ranked list of ``RetrievedDocument`` objects.
                       Must be non-empty.  Order is preserved exactly.

        Returns:
            Multi-line context string ready for prompt insertion.

        Raises:
            ContextBuildError: If *documents* is empty, contains non-
                               ``RetrievedDocument`` items, or if no
                               document fits within the token budget.
        """
        self._validate_input(documents)

        blocks: List[str] = []
        chars_used: int = 0

        for doc in documents:
            block = self._format_document(doc)
            block_chars = len(block)

            if chars_used + block_chars > self._char_budget:
                if not blocks:
                    # Not a single document fit — budget is dangerously small
                    raise ContextBuildError(
                        f"Context token budget ({self._config.context_token_budget} tokens "
                        f"= ~{self._char_budget} chars) is too small to fit even the "
                        f"first retrieved document ({block_chars} chars).  "
                        f"Increase LLMConfig.context_token_budget."
                    )
                logger.debug(
                    "ContextBuilder: budget reached after %d/%d documents "
                    "(%d chars used of %d).",
                    len(blocks),
                    len(documents),
                    chars_used,
                    self._char_budget,
                )
                break

            blocks.append(block)
            chars_used += block_chars

        context = _DOC_SEPARATOR.join(blocks)

        logger.info(
            "ContextBuilder: built context from %d/%d documents "
            "(%d chars, ~%d tokens).",
            len(blocks),
            len(documents),
            chars_used,
            chars_used // _CHARS_PER_TOKEN,
        )
        return context

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_document(doc: RetrievedDocument) -> str:
        """
        Format one ``RetrievedDocument`` into a labelled text block.

        The block includes every piece of provenance information that
        helps the LLM cite the source and assess relevance:
          * Rank and similarity score — prominence and confidence signal
          * Document ID — unique reference for citations
          * Source chat — which conversation this came from
          * Timestamp — when the messages were sent
          * Chunk index — position within the conversation

        The document text is placed last so the LLM sees the metadata
        header before the content, mirroring academic citation style.
        """
        meta = doc.metadata

        # Pull metadata fields with safe fallbacks
        source_chat = str(
            doc.metadata.get("source_chat", "") or ""
        ).strip() or "Unknown"
        chunk_index = meta.get("chunk_index", "N/A")
        start_ts = str(meta.get("start_timestamp", "") or "").strip()
        end_ts   = str(meta.get("end_timestamp",   "") or "").strip()

        if start_ts and end_ts and start_ts != end_ts:
            timestamp_str = f"{start_ts} to {end_ts}"
        elif start_ts:
            timestamp_str = start_ts
        elif end_ts:
            timestamp_str = end_ts
        else:
            timestamp_str = "N/A"

        lines = [
            f"[Document {doc.rank}]",
            f"Similarity : {doc.similarity_score:.4f}",
            f"ID         : {doc.document_id}",
            f"Source     : {source_chat}",
            f"Timestamp  : {timestamp_str}",
            f"Chunk      : {chunk_index}",
            "",
            doc.text,
        ]
        return "\n".join(lines)

    @staticmethod
    def _validate_input(documents: List[RetrievedDocument]) -> None:
        """
        Validate the document list before building context.

        Raises:
            ContextBuildError: On any validation failure.
        """
        if not isinstance(documents, list):
            raise ContextBuildError(
                f"ContextBuilder.build() expects a list, "
                f"got {type(documents).__name__}."
            )
        if len(documents) == 0:
            raise ContextBuildError(
                "ContextBuilder received an empty document list.  "
                "Ensure Phase 5 retrieval returned at least one result."
            )
        for i, doc in enumerate(documents):
            if not isinstance(doc, RetrievedDocument):
                raise ContextBuildError(
                    f"Item at index {i} is not a RetrievedDocument "
                    f"(got {type(doc).__name__}).  "
                    f"Only Phase 5 retrieval results may be passed to ContextBuilder."
                )
