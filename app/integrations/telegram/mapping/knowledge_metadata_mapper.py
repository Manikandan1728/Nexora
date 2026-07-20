"""
app/integrations/telegram/mapping/knowledge_metadata_mapper.py

[ADDITIVE] — New file. The single authoritative mapping between
KnowledgeObject and VectorMetadata.

This is the only place that knows both the source-independent KnowledgeObject
shape and the Telegram-specific optional fields that live in
KnowledgeObject.metadata. Content processors and chunkers must never read
Telegram-specific event formats directly — they call this mapper.

Requirement coverage: 2, 3, 4, 19 (structured logging).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from models.knowledge_object import KnowledgeObject
from models.vector_metadata import VectorMetadata

logger = logging.getLogger(__name__)


class KnowledgeMetadataMapper:
    """
    Maps a KnowledgeObject to a VectorMetadata instance.

    Usage
    -----
    ::

        mapper = KnowledgeMetadataMapper()
        vm = mapper.map(obj, chunk_index=0, content_part="text")
        chroma_meta = vm.to_vector_store_metadata()

    The mapper is stateless — all logic is in map().
    """

    def map(
        self,
        obj: KnowledgeObject,
        chunk_index: int = 0,
        content_part: str = "text",
        extra: dict[str, Any] | None = None,
    ) -> VectorMetadata:
        """
        Convert a KnowledgeObject into a VectorMetadata.

        Maps all required KnowledgeObject fields unconditionally, plus
        optional Telegram-specific extras from obj.metadata when present.
        Content processors pass specialized fields (page_number,
        slide_number, etc.) via the `extra` parameter.

        Args:
            obj:          The KnowledgeObject to map.
            chunk_index:  Zero-based index of this chunk within the content part.
            content_part: Content section being indexed ("text", "pdf", "image", etc.).
            extra:        Specialized scalar fields for this chunk
                          (page_number, slide_number, transcript_segment,
                          duration_seconds, frame_index, ocr_used,
                          caption_present, etc.). Must contain only
                          str/int/float/bool values.

        Returns:
            VectorMetadata ready for to_vector_store_metadata().

        Raises:
            ValueError: If obj is missing mandatory identity fields.
        """
        if not obj.owner_id:
            raise ValueError("KnowledgeObject.owner_id is required for metadata mapping.")
        if not obj.source:
            raise ValueError("KnowledgeObject.source is required for metadata mapping.")

        # --- Telegram-specific extras from obj.metadata ---
        tg_meta = obj.metadata or {}
        conversation_title = str(tg_meta.get("conversation_title", ""))
        conversation_type  = str(tg_meta.get("conversation_type", ""))
        attachment_id      = str(tg_meta.get("telegram_file_id", ""))

        # --- Coerce extra dict to scalar-only ---
        safe_extra: dict[str, str | int | float | bool] = {}
        if extra:
            for k, v in extra.items():
                coerced = _coerce_to_scalar(v)
                if coerced is not None:
                    safe_extra[k] = coerced

        vm = VectorMetadata(
            # Mandatory identity
            owner_id=obj.owner_id,
            source=obj.source,
            # Source identity
            source_account_id=obj.source_account_id,
            conversation_id=obj.conversation_id,
            conversation_title=conversation_title,
            conversation_type=conversation_type,
            # Sender — always by ID, never only by name
            sender_id=obj.sender_id or "",
            sender_name=obj.sender_name or "",
            # Message identity
            source_message_id=obj.source_message_id,
            content_type=obj.content_type,
            # Timing
            timestamp=_ensure_utc(obj.timestamp),
            # Attachment
            filename=obj.filename or "",
            mime_type=obj.mime_type or "",
            attachment_id=attachment_id,
            # Conversation structure
            reply_to_message_id=obj.reply_to_message_id or "",
            # Chunk position
            chunk_index=chunk_index,
            # Lifecycle
            is_edited=obj.is_edited,
            is_deleted=obj.is_deleted,
            # Specialized content fields
            extra=safe_extra,
        )

        logger.debug(
            "KnowledgeMetadataMapper: mapped owner=%r source=%r conv=%r "
            "msg=%r type=%r chunk_index=%d part=%r",
            obj.owner_id, obj.source, obj.conversation_id,
            obj.source_message_id, obj.content_type, chunk_index, content_part,
        )
        return vm

    def vector_document_id(
        self,
        obj: KnowledgeObject,
        content_part: str = "text",
        chunk_index: int = 0,
    ) -> str:
        """
        Generate the stable, deterministic vector document ID for a chunk.

        Delegates to KnowledgeObject.vector_document_id() — this is the
        single call site for ID generation so processors never construct
        IDs ad-hoc.

        Format: {source}:{account_id}:{conv_id}:{msg_id}:{content_part}:{chunk_index}
        """
        return obj.vector_document_id(content_part=content_part, chunk_index=chunk_index)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _ensure_utc(dt: datetime | None) -> datetime | None:
    """Ensure a datetime is timezone-aware (UTC) or return None."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _coerce_to_scalar(v: Any) -> str | int | float | bool | None:
    """Coerce a value to a ChromaDB-compatible scalar, or None if impossible."""
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return v
    if isinstance(v, str):
        return v
    if isinstance(v, datetime):
        return v.isoformat()
    if v is None:
        return ""
    try:
        return str(v)
    except Exception:
        return None
