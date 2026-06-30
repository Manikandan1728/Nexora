"""
app/documents/document_builder.py — Converts message chunks into Documents.

WHY THIS MODULE EXISTS
----------------------
The ``MessageChunker`` produces ``List[List[Message]]`` — raw groups of
messages.  Before these can be embedded, each group must become a
``Document``: a self-contained, metadata-rich text object.

The ``DocumentBuilder`` is responsible for:

1. **Formatting text** — converting a list of Message objects into the
   canonical ``"Sender: body\\nSender: body\\n..."`` text block that the
   embedding model will receive as input.

2. **Populating identity fields** — assigning a unique ID, recording which
   messages and participants belong to this chunk, and identifying the
   source chat.

3. **Timestamping** — recording the wall-clock span of the chunk so that
   retrieval can filter by date range.

4. **Attachment tracking** — collecting every attachment filename
   referenced by messages in the chunk.

The builder does *not* generate rich metadata statistics (message count,
media flags, conversation duration) — that is the responsibility of the
``MetadataEnricher``, which runs after the builder.

TEXT FORMAT RATIONALE
---------------------
``"Sender: message"`` is the format WhatsApp uses natively in exports.
It is already familiar to the embedding model through its training data,
and it keeps speaker attribution visible within the text so the model
can differentiate who said what without needing to inspect metadata.
"""

from __future__ import annotations

import logging
from typing import List

from models.message import Message
from models.document import Document, make_document_id
from app.documents.tokenizer_service import TokenizerService
from exceptions.exceptions import DocumentBuildError

logger = logging.getLogger(__name__)


class DocumentBuilder:
    """
    Converts message chunks (``List[List[Message]]``) into ``List[Document]``.

    Parameters
    ----------
    tokenizer_service : TokenizerService
        Used to record the exact token count of each document's text field.
    source_chat : str
        A human-readable label identifying the originating chat.
        Typically constructed as ``"Alice & Bob"`` from participant names.
    """

    def __init__(
        self,
        tokenizer_service: TokenizerService,
        source_chat: str = "Unknown Chat",
    ) -> None:
        self._tokenizer = tokenizer_service
        self._source_chat = source_chat

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, chunks: List[List[Message]]) -> List[Document]:
        """
        Convert a list of message chunks into a list of ``Document`` objects.

        Args:
            chunks: Output of ``MessageChunker.chunk()``.  Each inner list
                    is a group of ``Message`` objects forming one chunk.

        Returns:
            Ordered list of ``Document`` objects.  The order matches the
            chunk order so ``Document.chunk_index`` is meaningful.

        Raises:
            DocumentBuildError: If a chunk cannot be converted (e.g. all
                                 messages have empty bodies).
        """
        if not chunks or chunks == [[]]:
            logger.debug("DocumentBuilder received empty chunk list; returning [].")
            return []

        documents: List[Document] = []

        for index, chunk in enumerate(chunks):
            if not chunk:
                logger.debug("Skipping empty chunk at index %d.", index)
                continue
            try:
                doc = self._build_single(chunk, index)
                documents.append(doc)
            except Exception as exc:
                raise DocumentBuildError(
                    f"Failed to build document for chunk index {index}: {exc}"
                ) from exc

        logger.debug(
            "DocumentBuilder produced %d documents from %d chunks.",
            len(documents),
            len(chunks),
        )
        return documents

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_single(self, chunk: List[Message], chunk_index: int) -> Document:
        """
        Build a single ``Document`` from a message chunk.

        Args:
            chunk: Non-empty list of ``Message`` objects.
            chunk_index: Zero-based position of this chunk.

        Returns:
            A populated, immutable ``Document`` instance.
        """
        text = self._format_text(chunk)
        token_count = self._tokenizer.count_tokens(text)
        participants = self._extract_participants(chunk)
        attachments = self._extract_attachments(chunk)
        message_ids = tuple(msg.id for msg in chunk)
        start_ts = chunk[0].timestamp if chunk else ""
        end_ts = chunk[-1].timestamp if chunk else ""

        return Document(
            id=make_document_id(),
            text=text,
            metadata={},          # populated later by MetadataEnricher
            participants=participants,
            attachments=attachments,
            message_ids=message_ids,
            source_chat=self._source_chat,
            chunk_index=chunk_index,
            token_count=token_count,
            start_timestamp=start_ts,
            end_timestamp=end_ts,
        )

    @staticmethod
    def _format_text(chunk: List[Message]) -> str:
        """
        Format a list of messages into a single text block.

        Format: ``"Sender: message\\nSender: message\\n..."``

        System messages are included verbatim with the ``"SYSTEM: "`` prefix
        so the model is aware of system events (encryption notices, etc.)
        but they can be filtered out during retrieval if desired.

        Args:
            chunk: Non-empty list of ``Message`` objects.

        Returns:
            Multi-line text string.
        """
        lines: List[str] = []
        for msg in chunk:
            # Preserve multi-line message bodies by replacing interior
            # newlines with a space to keep each message on a logical single
            # line in the document.  This prevents the tokenizer from treating
            # continuation lines as separate utterances.
            body = msg.message.replace("\n", " ").strip()
            lines.append(f"{msg.sender}: {body}")
        return "\n".join(lines)

    @staticmethod
    def _extract_participants(chunk: List[Message]) -> tuple:
        """
        Collect the sorted, unique set of non-SYSTEM senders in *chunk*.

        Returns:
            Sorted tuple of participant names.
        """
        names = sorted({
            msg.sender
            for msg in chunk
            if msg.sender and msg.sender != "SYSTEM"
        })
        return tuple(names)

    @staticmethod
    def _extract_attachments(chunk: List[Message]) -> tuple:
        """
        Collect all attachment references from messages in *chunk*.

        Only messages with ``message_type == 'attachment'`` and a non-empty
        ``attachment`` field contribute.

        Returns:
            Tuple of attachment filename/reference strings.
        """
        refs = [
            msg.attachment
            for msg in chunk
            if msg.message_type == "attachment" and msg.attachment
        ]
        return tuple(refs)
