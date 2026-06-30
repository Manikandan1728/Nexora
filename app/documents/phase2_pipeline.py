"""
app/documents/phase2_pipeline.py — Phase 2 orchestrator.

WHY THIS MODULE EXISTS
----------------------
Each of the six Phase 2 sub-components (Cleaner, Normalizer,
TokenizerService, Chunker, DocumentBuilder, MetadataEnricher) has a single
responsibility.  The pipeline's job is to wire them together in the correct
order and provide one clean entry point for callers.

Callers only need to know:

    docs = Phase2Pipeline(chat).run()

Everything else — tokenizer loading, configuration, ordering — is an
internal concern of this class.

PIPELINE STAGES
---------------
1. TextCleaner      — Remove Unicode artefacts, normalise whitespace
2. TextNormalizer   — NFC, sender names, typographic punctuation
3. TokenizerService — Load BGE-M3 tokenizer (singleton, loaded once)
4. MessageChunker   — Group messages into token-bounded overlapping chunks
5. DocumentBuilder  — Convert each chunk into a Document object
6. MetadataEnricher — Populate Document.metadata with computed statistics

PERFORMANCE
-----------
For 100k+ message conversations:
* The tokenizer is a singleton — loaded once per process.
* Token counts are cached inside TokenizerService — each unique formatted
  message is tokenized exactly once even if it appears in multiple overlap
  windows.
* Cleaning and normalisation are O(n) single passes over message bodies.
* No intermediate copies of the full message list are kept beyond the
  current chunk window.

CONFIGURABILITY
---------------
``ChunkerConfig`` is injected so tests and callers can override
``max_tokens`` and ``overlap_tokens`` without subclassing.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from models.chat import Chat
from models.document import Document
from models.message import Message

from app.documents.cleaner import TextCleaner
from app.documents.normalizer import TextNormalizer
from app.documents.tokenizer_service import TokenizerService
from app.documents.chunker import MessageChunker, ChunkerConfig
from app.documents.document_builder import DocumentBuilder
from app.documents.metadata_enricher import MetadataEnricher

logger = logging.getLogger(__name__)


class Phase2Pipeline:
    """
    Orchestrates the conversion of a ``Chat`` object into ``List[Document]``.

    Parameters
    ----------
    chat : Chat
        A fully populated ``Chat`` object produced by ``Phase1Pipeline``.
    config : ChunkerConfig, optional
        Token limits for the chunker.  Defaults to 450 max / 50 overlap.
    max_cache_size : int
        Maximum number of entries in the tokenizer's token-count cache.
        Defaults to 50,000.

    Example
    -------
    ::

        from pipeline.phase1_pipeline import Phase1Pipeline
        from app.documents.phase2_pipeline import Phase2Pipeline

        chat = Phase1Pipeline("export.zip").run()
        documents = Phase2Pipeline(chat).run()
        # documents is List[Document]
    """

    def __init__(
        self,
        chat: Chat,
        config: Optional[ChunkerConfig] = None,
        max_cache_size: int = 50_000,
    ) -> None:
        if not isinstance(chat, Chat):
            raise TypeError(f"Expected Chat, got {type(chat).__name__}.")

        self._chat = chat
        self._config = config or ChunkerConfig()
        self._max_cache_size = max_cache_size

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> List[Document]:
        """
        Execute the full Phase 2 pipeline.

        Returns:
            Ordered ``List[Document]`` ready for Phase 3 embedding.
            Returns an empty list when the chat has no messages.
        """
        logger.info(
            "Phase 2 pipeline starting.  Messages: %d  Participants: %s",
            len(self._chat.messages),
            self._chat.participants,
        )

        if not self._chat.messages:
            logger.warning("Chat contains no messages; Phase 2 returns [].")
            return []

        # ── Stage 1 & 2: Clean + Normalise messages ──────────────────
        cleaned_messages = self._clean_and_normalise(self._chat.messages)
        logger.debug("Stage 1-2 complete: cleaned and normalised %d messages.", len(cleaned_messages))

        # ── Stage 3: Load tokenizer (singleton — may already be loaded) ─
        tokenizer = TokenizerService(max_cache_size=self._max_cache_size)

        # ── Stage 4: Chunk messages ────────────────────────────────────
        chunker = MessageChunker(tokenizer_service=tokenizer, config=self._config)
        chunks = chunker.chunk(cleaned_messages)
        logger.debug("Stage 4 complete: produced %d chunks.", len(chunks))

        # ── Stage 5: Build Document objects ───────────────────────────
        source_label = self._build_source_label()
        builder = DocumentBuilder(
            tokenizer_service=tokenizer,
            source_chat=source_label,
        )
        documents = builder.build(chunks)
        logger.debug("Stage 5 complete: built %d documents.", len(documents))

        # ── Stage 6: Enrich metadata ───────────────────────────────────
        enricher = MetadataEnricher()
        documents = enricher.enrich(documents)
        logger.debug("Stage 6 complete: enriched %d documents.", len(documents))

        logger.info(
            "Phase 2 pipeline complete.  Documents produced: %d  "
            "Token cache entries: %d",
            len(documents),
            tokenizer.cache_size,
        )
        return documents

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _clean_and_normalise(self, messages: List[Message]) -> List[Message]:
        """
        Return a new list of ``Message`` objects with cleaned and
        normalised text bodies and sender names.

        The original ``Message`` objects are never mutated — new instances
        are created via dataclass replacement where necessary.

        Args:
            messages: Original message list from the Chat.

        Returns:
            New list of Message objects with cleaned/normalised content.
        """
        import dataclasses

        result: List[Message] = []
        for msg in messages:
            # Clean the body
            clean_body = TextCleaner.clean_message_body(msg.message)
            # Normalise the body text (NFC + typographic punctuation)
            norm_body = TextNormalizer.normalize_text(clean_body)
            # Normalise the sender name
            norm_sender = TextNormalizer.normalize_sender_name(msg.sender)
            # Normalise the timestamp string
            norm_ts = TextNormalizer.normalize_timestamp(msg.timestamp)

            # Only create a new Message if something changed (saves memory for
            # conversations where most messages are already clean)
            if (
                norm_body != msg.message
                or norm_sender != msg.sender
                or norm_ts != msg.timestamp
            ):
                result.append(dataclasses.replace(
                    msg,
                    message=norm_body,
                    sender=norm_sender,
                    timestamp=norm_ts,
                ))
            else:
                result.append(msg)

        return result

    def _build_source_label(self) -> str:
        """
        Build a human-readable source label from the chat participants.

        Examples:
            ["Alice", "Bob"]           → "Alice & Bob"
            ["Alice", "Bob", "Carol"]  → "Alice, Bob & Carol"
            []                         → "Unknown Chat"
        """
        participants = self._chat.participants
        if not participants:
            return "Unknown Chat"
        if len(participants) == 1:
            return participants[0]
        if len(participants) == 2:
            return f"{participants[0]} & {participants[1]}"
        return ", ".join(participants[:-1]) + f" & {participants[-1]}"
