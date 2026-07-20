"""
models/knowledge_object.py — Source-independent domain model for Nexora.

Nexora is a Telegram AI Knowledge Retrieval Platform.
Telegram is the sole supported messaging data source.

KnowledgeObject is the canonical unit of content flowing through the
Nexora processing pipeline:
  - Telegram messages (text, link, document, image, voice, video)
  - Future sources may be added without changing this model

DESIGN PRINCIPLES
-----------------
1. Stable identity: (owner_id, source, source_account_id, conversation_id,
   source_message_id) — never display names.

2. Sender by ID: sender_id is the retrieval key; sender_name is display-only.

3. Content flexibility: supports text, PDF, DOCX, PPTX, image, voice, video, link.

4. Edit/delete awareness: is_edited and is_deleted allow Telegram sync.

5. Owner isolation: owner_id is the primary security boundary.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


class KnowledgeObject(BaseModel):
    """
    Source-independent content unit for the Nexora processing pipeline.

    Attributes
    ----------
    owner_id : str
        The user account that owns this content. Primary security boundary.
        Every retrieval query MUST include an owner_id filter.

    source : str
        The originating platform. Currently always "telegram".

    source_account_id : str
        The connected Telegram account ID.

    conversation_id : str
        Stable Telegram chat ID.

    source_message_id : str
        The Telegram message ID.

    sender_id : str | None
        Stable sender identifier. Never use sender_name for retrieval.

    sender_name : str | None
        Display name only. Never use as a retrieval filter.

    content_type : str
        Routes to the appropriate content processor.

    text : str | None
        Textual content of the message.

    file_path : str | None
        Local path to the downloaded attachment. Relative to media root.

    filename : str | None
        Original attachment filename.

    mime_type : str | None
        MIME type of the attachment.

    timestamp : datetime
        When the message was sent. Always timezone-aware.

    reply_to_message_id : str | None
        source_message_id of the replied-to message, if any.

    forwarded_from : str | None
        Original author for forwarded messages (display only).

    is_edited : bool
        True when this is an edited version of a previously indexed message.

    is_deleted : bool
        True when this message has been deleted on Telegram.

    indexing_enabled_at : datetime | None
        Messages before this timestamp must not be indexed.

    metadata : dict[str, Any]
        Source-specific extras (forward_date, media_group_id, etc.).
    """

    owner_id: str
    source: str
    source_account_id: str
    conversation_id: str
    source_message_id: str

    sender_id: Optional[str] = None
    sender_name: Optional[str] = None

    content_type: str
    text: Optional[str] = None

    file_path: Optional[str] = None
    filename: Optional[str] = None
    mime_type: Optional[str] = None

    timestamp: datetime

    reply_to_message_id: Optional[str] = None
    forwarded_from: Optional[str] = None

    is_edited: bool = False
    is_deleted: bool = False

    indexing_enabled_at: Optional[datetime] = None
    chunk_hint: Optional[str] = None

    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": False}

    @property
    def has_text(self) -> bool:
        return bool(self.text and self.text.strip())

    @property
    def has_attachment(self) -> bool:
        return bool(self.file_path or self.filename)

    @property
    def is_indexable(self) -> bool:
        if self.is_deleted:
            return False
        if not (self.has_text or self.has_attachment):
            return False
        if self.indexing_enabled_at is not None:
            return self.timestamp >= self.indexing_enabled_at
        return True

    @property
    def stable_id(self) -> str:
        return f"{self.source}:{self.source_account_id}:{self.conversation_id}:{self.source_message_id}"

    def vector_document_id(self, content_part: str = "text", chunk_index: int = 0) -> str:
        """
        Stable, deterministic vector document ID for a specific chunk.
        Format: {source}:{account_id}:{conv_id}:{msg_id}:{content_part}:{chunk_index}
        """
        return f"{self.stable_id}:{content_part}:{chunk_index}"

    def __repr__(self) -> str:
        return (
            f"KnowledgeObject(source={self.source!r}, owner={self.owner_id!r}, "
            f"conv={self.conversation_id!r}, msg={self.source_message_id!r}, "
            f"type={self.content_type!r}, edited={self.is_edited}, deleted={self.is_deleted})"
        )


SUPPORTED_CONTENT_TYPES: frozenset[str] = frozenset({
    "text", "link", "pdf", "docx", "pptx",
    "image", "voice", "video", "sticker", "document", "system",
})


def is_supported_content_type(content_type: str) -> bool:
    return content_type in SUPPORTED_CONTENT_TYPES
