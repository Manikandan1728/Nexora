"""
app/documents/metadata_enricher.py — Enriches Documents with computed metadata.

WHY THIS MODULE EXISTS
----------------------
The ``DocumentBuilder`` produces ``Document`` objects with an empty
``metadata`` dict.  Before the documents reach the embedding pipeline,
that dict must be populated with statistics that are useful for:

1. **Vector store filtering** — e.g. retrieve only documents that
   ``contains_images == True`` or whose ``conversation_duration`` is
   within a date range.
2. **Result ranking** — a chunk with a high ``message_count`` or
   ``participant_count`` may be a richer result than a sparse one.
3. **Debugging / observability** — knowing the ``average_message_length``
   and ``attachment_count`` of a retrieved chunk helps trace why a
   particular answer was returned.

The enricher is intentionally a separate pipeline stage rather than being
merged into the builder, following the Single Responsibility Principle.
The builder focuses on structure; the enricher focuses on analytics.

IMMUTABILITY WORKAROUND
-----------------------
``Document`` is a ``frozen=True`` dataclass, so its fields cannot be
mutated after creation.  The enricher uses ``dataclasses.replace()`` to
produce a *new* ``Document`` instance with the populated ``metadata``
dict, leaving the original unchanged.  This preserves immutability
semantics while allowing post-construction enrichment.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import List

from models.document import Document
from models.message import Message
from utils.datetime_utils import DateTimeUtils

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Attachment media type → metadata flag mapping
# ---------------------------------------------------------------------------
_IMAGE_EXTS = frozenset({
    "jpg", "jpeg", "png", "gif", "webp", "bmp", "tiff", "heic", "heif",
    "image",   # WhatsApp omission keyword
    "sticker",
})
_AUDIO_EXTS = frozenset({
    "mp3", "ogg", "aac", "m4a", "opus", "wav", "flac", "wma",
    "audio",   # WhatsApp omission keyword
    "ptt",     # Push-to-talk voice notes
})
_VIDEO_EXTS = frozenset({
    "mp4", "mkv", "mov", "avi", "wmv", "flv", "webm", "3gp",
    "video",   # WhatsApp omission keyword
})
_DOCUMENT_EXTS = frozenset({
    "pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt", "txt", "csv",
    "document", # WhatsApp omission keyword
})


class MetadataEnricher:
    """
    Adds computed statistics to the ``metadata`` dict of each ``Document``.

    All computation is deterministic and depends only on the ``Document``
    object's existing fields — no external I/O or model calls are made.

    Usage
    -----
    ::

        enricher = MetadataEnricher()
        enriched_docs = enricher.enrich(documents)
    """

    def enrich(self, documents: List[Document]) -> List[Document]:
        """
        Produce a new list of ``Document`` objects with ``metadata`` filled.

        The input list is not mutated.

        Args:
            documents: List of ``Document`` objects produced by
                       ``DocumentBuilder.build()``.

        Returns:
            New list of ``Document`` objects with populated ``metadata``.
        """
        if not documents:
            return []

        enriched: List[Document] = []
        for doc in documents:
            enriched.append(self._enrich_single(doc))

        logger.debug("MetadataEnricher enriched %d documents.", len(enriched))
        return enriched

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _enrich_single(self, doc: Document) -> Document:
        """
        Compute metadata for one document and return a new Document with
        the metadata dict populated.

        Generated keys
        --------------
        message_count : int
            Number of messages in this chunk.
        participant_count : int
            Number of distinct non-SYSTEM participants in this chunk.
        contains_images : bool
            True if any attachment in this chunk is an image or sticker.
        contains_audio : bool
            True if any attachment in this chunk is an audio file / voice note.
        contains_video : bool
            True if any attachment in this chunk is a video file.
        contains_documents : bool
            True if any attachment in this chunk is a document file.
        attachment_count : int
            Total number of attachment references in this chunk.
        conversation_duration_seconds : float
            Wall-clock seconds between the first and last message in the
            chunk.  0.0 when timestamps are unparseable or identical.
        average_message_length : float
            Mean character count of message bodies in this chunk (before
            formatting).
        chunk_index : int
            Mirrors ``Document.chunk_index`` for easy access without
            loading the full Document model at the metadata-filter level.
        token_count : int
            Mirrors ``Document.token_count``.
        """
        # -- Attachment flags --
        attachment_flags = self._classify_attachments(doc.attachments)

        # -- Conversation duration --
        duration = self._compute_duration(doc.start_timestamp, doc.end_timestamp)

        # -- Average message length --
        avg_len = self._compute_average_length(doc.text)

        metadata = {
            "message_count": len(doc.message_ids),
            "participant_count": len(doc.participants),
            "contains_images": attachment_flags["has_image"],
            "contains_audio": attachment_flags["has_audio"],
            "contains_video": attachment_flags["has_video"],
            "contains_documents": attachment_flags["has_document"],
            "attachment_count": len(doc.attachments),
            "conversation_duration_seconds": duration,
            "average_message_length": avg_len,
            "chunk_index": doc.chunk_index,
            "token_count": doc.token_count,
            "source_chat": doc.source_chat,
        }

        # dataclasses.replace() creates a new frozen instance with metadata set
        return dataclasses.replace(doc, metadata=metadata)

    @staticmethod
    def _classify_attachments(attachments: tuple) -> dict:
        """
        Classify attachment references by media type.

        Args:
            attachments: Tuple of attachment filename/reference strings.

        Returns:
            Dict with boolean flags for each media category.
        """
        flags = {
            "has_image": False,
            "has_audio": False,
            "has_video": False,
            "has_document": False,
        }
        for ref in attachments:
            if not ref:
                continue
            # Try to get extension; fall back to the whole string for
            # WhatsApp omission keywords like "image omitted"
            lower = ref.lower()
            # Extract extension if present
            ext = lower.rsplit(".", 1)[-1] if "." in lower else lower.split()[0]

            if ext in _IMAGE_EXTS or any(k in lower for k in ("image", "sticker")):
                flags["has_image"] = True
            if ext in _AUDIO_EXTS or any(k in lower for k in ("audio", "ptt")):
                flags["has_audio"] = True
            if ext in _VIDEO_EXTS or "video" in lower:
                flags["has_video"] = True
            if ext in _DOCUMENT_EXTS or "document" in lower:
                flags["has_document"] = True

        return flags

    @staticmethod
    def _compute_duration(start_ts: str, end_ts: str) -> float:
        """
        Compute the duration in seconds between *start_ts* and *end_ts*.

        Returns 0.0 when either timestamp is missing or unparseable.
        """
        if not start_ts or not end_ts:
            return 0.0
        try:
            start_dt = DateTimeUtils.parse_timestamp(start_ts)
            end_dt = DateTimeUtils.parse_timestamp(end_ts)
            delta = (end_dt - start_dt).total_seconds()
            return max(0.0, delta)
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _compute_average_length(text: str) -> float:
        """
        Compute the mean character count per line in *text*.

        Each line in the document text corresponds to one message
        (``"Sender: body"``).  We measure the length of the *body* portion
        (after the first ``": "``), not the full line, to exclude the
        constant sender-name overhead.

        Returns 0.0 for empty text.
        """
        if not text:
            return 0.0
        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            return 0.0
        lengths: List[float] = []
        for line in lines:
            # Strip "Sender: " prefix to measure body length
            if ": " in line:
                body = line.split(": ", 1)[1]
            else:
                body = line
            lengths.append(float(len(body)))
        return sum(lengths) / len(lengths)
