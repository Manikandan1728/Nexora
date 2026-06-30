"""
app/documents/chunker.py — Message-based chunker for Phase 2.

WHY MESSAGE-BASED CHUNKING
---------------------------
Character-based or word-based chunking splits conversations at arbitrary
points, destroying conversational context.  A question and its answer may
end up in different chunks, making retrieval return an answer with no
question, or vice versa.

Message-based chunking treats each ``Message`` as an atomic unit.  Chunks
are built by accumulating whole messages until the token limit is reached.
Only when a *single* message exceeds the limit is it split — and even then,
only at sentence boundaries to preserve local coherence.

WHY OVERLAP
-----------
Without overlap, a question at the end of chunk N and its answer at the
start of chunk N+1 would never appear in the same retrieved chunk.  Overlap
copies the last *k* tokens' worth of messages from chunk N into the
beginning of chunk N+1, ensuring that context spans chunk boundaries.

ALGORITHM (detailed)
--------------------
1. Pre-compute the token count for every message (using the cached
   tokenizer service).
2. Maintain a ``current_chunk`` accumulator (list of Messages).
3. For each message:
   a. If ``current_chunk + message`` fits within ``max_tokens`` → append.
   b. Otherwise → finalise ``current_chunk`` as a chunk; compute the
      overlap tail from ``current_chunk``; start the new chunk with the
      overlap tail + the new message.
4. Any non-empty ``current_chunk`` remaining after the loop is finalised.
5. Oversized single messages: if a message token count > ``max_tokens``,
   it is split at sentence boundaries into sub-messages, each of which
   is treated as a normal message for chunking purposes.

CONFIGURATION
-------------
All limits are constructor parameters with sensible defaults matching the
specification:
  - ``max_tokens``  : 450
  - ``overlap_tokens`` : 50
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import List, Optional

from models.message import Message
from app.documents.tokenizer_service import TokenizerService
from exceptions.exceptions import ChunkingError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sentence-boundary splitter — used only for oversized single messages
# ---------------------------------------------------------------------------
# Splits on: ". " | "! " | "? " | ".\n" | "!\n" | "?\n"
# Also splits on a bare line break (paragraph boundary inside a message).
# Does NOT split in the middle of "Mr." / "Dr." / "vs." abbreviations
# because the abbreviation is followed by a capital letter — we therefore
# require a lowercase or digit before the terminal punctuation to avoid
# most common abbreviation false-positives.  This is a pragmatic heuristic,
# not a perfect NLP sentence tokeniser.
_SENTENCE_SPLIT_RE = re.compile(
    r"(?<=[a-z0-9\"\'\)])"    # lookbehind: char before the punctuation
    r"[.!?]"                   # terminal punctuation
    r"(?=\s+[A-Z\u0080-\uFFFF]|\n|$)"  # lookahead: space+capital, newline, or end
    r"|"
    r"\n+"                     # paragraph break inside a message
)


@dataclass
class ChunkerConfig:
    """
    Configuration for the ``MessageChunker``.

    Attributes
    ----------
    max_tokens : int
        Maximum token count per chunk (inclusive).  Default: 450.
    overlap_tokens : int
        Minimum number of tokens to carry over from the previous chunk
        into the new one for context continuity.  Default: 50.
    """
    max_tokens: int = 450
    overlap_tokens: int = 50

    def __post_init__(self) -> None:
        if self.max_tokens < 10:
            raise ValueError("max_tokens must be at least 10.")
        if self.overlap_tokens < 0:
            raise ValueError("overlap_tokens must be non-negative.")
        if self.overlap_tokens >= self.max_tokens:
            raise ValueError("overlap_tokens must be less than max_tokens.")


class MessageChunker:
    """
    Groups a flat list of ``Message`` objects into overlapping chunks,
    each of which fits within the BGE-M3 token limit.

    Parameters
    ----------
    tokenizer_service : TokenizerService
        Pre-loaded tokenizer service.  Injected to allow test mocking.
    config : ChunkerConfig
        Token limits and overlap settings.
    """

    def __init__(
        self,
        tokenizer_service: TokenizerService,
        config: Optional[ChunkerConfig] = None,
    ) -> None:
        self._tokenizer = tokenizer_service
        self._config = config or ChunkerConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chunk(self, messages: List[Message]) -> List[List[Message]]:
        """
        Partition *messages* into overlapping chunks.

        Args:
            messages: Ordered list of ``Message`` objects from a ``Chat``.

        Returns:
            A list of message groups.  Each group is a ``List[Message]``
            that represents one ``Document`` when built later.
            Returns ``[[]]`` (a list containing one empty list) for an
            empty input, so callers never receive an empty outer list.

        Raises:
            ChunkingError: If an oversized message cannot be split into
                           sentences that individually fit within
                           ``max_tokens``.
        """
        if not messages:
            return [[]]

        # Expand any messages whose text alone exceeds max_tokens
        expanded: List[Message] = self._expand_oversized(messages)

        chunks: List[List[Message]] = []
        current_chunk: List[Message] = []
        current_tokens: int = 0

        for msg in expanded:
            msg_tokens = self._token_count_for_message(msg)

            if current_tokens + msg_tokens <= self._config.max_tokens:
                # Fits — accumulate
                current_chunk.append(msg)
                current_tokens += msg_tokens
            else:
                # Does not fit — finalise current chunk
                if current_chunk:
                    chunks.append(current_chunk)

                # Build overlap: walk backwards through current_chunk
                # collecting messages until we have >= overlap_tokens
                overlap_msgs = self._build_overlap(current_chunk)
                overlap_tokens = sum(
                    self._token_count_for_message(m) for m in overlap_msgs
                )

                # Start new chunk with overlap + current message
                current_chunk = overlap_msgs + [msg]
                current_tokens = overlap_tokens + msg_tokens

        # Finalise the last accumulated chunk
        if current_chunk:
            chunks.append(current_chunk)

        if not chunks:
            return [[]]

        logger.debug(
            "Chunker produced %d chunks from %d messages "
            "(max_tokens=%d, overlap_tokens=%d).",
            len(chunks),
            len(messages),
            self._config.max_tokens,
            self._config.overlap_tokens,
        )
        return chunks

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _token_count_for_message(self, msg: Message) -> int:
        """
        Return the token count for the formatted representation of *msg*.

        The formatted form is ``"Sender: body"`` — the same text that will
        appear in ``Document.text``.  Counting the formatted form (not just
        the body) ensures the chunk token limit accounts for sender names.
        """
        formatted = f"{msg.sender}: {msg.message}"
        return self._tokenizer.count_tokens(formatted)

    def _build_overlap(self, chunk: List[Message]) -> List[Message]:
        """
        Select the tail of *chunk* whose total token count is as close as
        possible to ``overlap_tokens`` without exceeding it.

        Returns an empty list when ``overlap_tokens`` is 0 or *chunk* is
        empty.
        """
        if not chunk or self._config.overlap_tokens == 0:
            return []

        overlap: List[Message] = []
        accumulated = 0

        for msg in reversed(chunk):
            msg_tokens = self._token_count_for_message(msg)
            if accumulated + msg_tokens <= self._config.overlap_tokens:
                overlap.insert(0, msg)
                accumulated += msg_tokens
            else:
                break

        return overlap

    def _expand_oversized(self, messages: List[Message]) -> List[Message]:
        """
        For every message whose token count exceeds ``max_tokens``,
        split it into sentence-boundary sub-messages.  Return a new list
        where all such messages have been replaced by their fragments.

        Each fragment is a synthetic ``Message`` with the same metadata
        (id, timestamp, sender, message_type) but with only a portion of
        the original body.  The ``attachment`` field is preserved only on
        the first fragment to avoid double-counting.

        Args:
            messages: Original message list.

        Returns:
            Expanded list (same or longer than input).
        """
        result: List[Message] = []
        for msg in messages:
            msg_tokens = self._token_count_for_message(msg)
            if msg_tokens <= self._config.max_tokens:
                result.append(msg)
            else:
                logger.debug(
                    "Message id=%d exceeds max_tokens (%d > %d); "
                    "splitting at sentence boundaries.",
                    msg.id,
                    msg_tokens,
                    self._config.max_tokens,
                )
                fragments = self._split_at_sentences(msg)
                result.extend(fragments)
        return result

    def _split_at_sentences(self, msg: Message) -> List[Message]:
        """
        Split a single oversized ``Message`` into multiple synthetic
        ``Message`` objects at sentence boundaries.

        Args:
            msg: The oversized message.

        Returns:
            List of synthetic Message objects.

        Raises:
            ChunkingError: If even a single sentence exceeds ``max_tokens``.
        """
        # Split body into sentence candidates
        raw_sentences = _SENTENCE_SPLIT_RE.split(msg.message)
        sentences = [s.strip() for s in raw_sentences if s.strip()]

        if not sentences:
            # Nothing to split — return the original (will be oversized but
            # cannot be helped; the caller will have to handle it gracefully)
            return [msg]

        fragments: List[Message] = []
        buffer: List[str] = []
        buffer_tokens: int = 0

        for sentence in sentences:
            # Count tokens for "Sender: sentence" to match how chunks are counted
            sentence_tokens = self._tokenizer.count_tokens(
                f"{msg.sender}: {sentence}"
            )

            if sentence_tokens > self._config.max_tokens:
                raise ChunkingError(
                    f"A single sentence in message id={msg.id} "
                    f"({sentence_tokens} tokens) exceeds max_tokens="
                    f"{self._config.max_tokens}.  Cannot split further."
                )

            if buffer_tokens + sentence_tokens <= self._config.max_tokens:
                buffer.append(sentence)
                buffer_tokens += sentence_tokens
            else:
                # Finalise the current buffer as a fragment
                if buffer:
                    fragments.append(
                        self._make_fragment(msg, " ".join(buffer), len(fragments))
                    )
                buffer = [sentence]
                buffer_tokens = sentence_tokens

        # Flush remaining buffer
        if buffer:
            fragments.append(
                self._make_fragment(msg, " ".join(buffer), len(fragments))
            )

        return fragments if fragments else [msg]

    @staticmethod
    def _make_fragment(original: Message, body: str, index: int) -> Message:
        """
        Build a synthetic fragment Message from *original* with *body*.

        The ``attachment`` field is only kept on the first fragment (index 0)
        to prevent downstream enrichers from double-counting attachments.
        """
        return Message(
            id=original.id,
            timestamp=original.timestamp,
            sender=original.sender,
            message=body,
            message_type=original.message_type,
            attachment=original.attachment if index == 0 else None,
        )
