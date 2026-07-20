"""
app/integrations/telegram/mapping/telegram_normalizer.py

[ADDITIVE] — New file. No existing code is modified.

Converts Telegram event dictionaries (from mock fixtures or TDLib updates)
into Nexora KnowledgeObject instances.

RESPONSIBILITIES
----------------
- Accept mock Telegram events (dict) now; accept TDLib update objects later
  via a thin adapter layer (not yet implemented).
- Resolve source account, conversation ID, sender ID.
- Detect message type and map to KnowledgeObject content_type.
- Extract message text and attachment metadata.
- Preserve reply and forwarding information.
- Convert timestamps to timezone-aware datetime objects.
- Produce one or more KnowledgeObject instances per event.

WHAT THIS CLASS DOES NOT DO
----------------------------
- No parsing or embedding logic.
- No database writes.
- No policy checks (those live in TelegramIngestionPolicy).
- No content extraction (PDF text, image OCR) — those are downstream.

OWNER_ID REQUIREMENT
--------------------
owner_id is required and must be passed by the caller. The normalizer
never infers owner_id from the event itself — it is always provided
by the application layer that owns the Telegram account context.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from models.knowledge_object import KnowledgeObject
from app.integrations.telegram.mapping.content_type_mapper import ContentTypeMapper
from app.integrations.telegram.mapping.sender_resolver import SenderResolver

logger = logging.getLogger(__name__)


class TelegramNormalizer:
    """
    Converts a raw Telegram event dict into one or more KnowledgeObject
    instances ready for the Nexora processing pipeline.

    Usage
    -----
    ::

        normalizer = TelegramNormalizer()
        objects = normalizer.normalize(event, owner_id="user_123")
        # objects is List[KnowledgeObject]

    Currently accepts mock event dicts; will accept TDLib update objects
    once TDLibTelegramClient is implemented (Phase 15). The interface
    remains the same — only the input type will be extended via an
    overloaded normalize() or a separate normalize_tdlib_update() method.
    """

    def __init__(self) -> None:
        self._content_type_mapper = ContentTypeMapper()
        self._sender_resolver = SenderResolver()

    def normalize(
        self,
        event: dict[str, Any],
        owner_id: str,
        indexing_enabled_at: datetime | None = None,
    ) -> list[KnowledgeObject]:
        """
        Convert one Telegram event dict into KnowledgeObject instances.

        For most messages: returns a single KnowledgeObject.
        For messages with both text and an attachment: returns two objects
        (one for text content, one for the attachment) — allowing the
        pipeline to process each through its appropriate content processor.

        Args:
            event:               Raw Telegram event dict.
            owner_id:            The Nexora owner who owns this Telegram account.
            indexing_enabled_at: Activation timestamp for this chat. Messages
                                 before this time will have is_indexable=False
                                 (set via KnowledgeObject.indexing_enabled_at).

        Returns:
            List of KnowledgeObject instances (1 or 2 per event).
            Returns an empty list when the event cannot be normalized
            (logged as a warning, never raised).
        """
        try:
            return self._normalize_inner(event, owner_id, indexing_enabled_at)
        except Exception as exc:
            logger.warning(
                "TelegramNormalizer: failed to normalize event %r: %s",
                event.get("message_id", "?"),
                exc,
            )
            return []

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _normalize_inner(
        self,
        event: dict[str, Any],
        owner_id: str,
        indexing_enabled_at: datetime | None,
    ) -> list[KnowledgeObject]:
        # --- Required identity fields ---
        account_id = str(event.get("account_id", ""))
        chat_id = str(event.get("chat_id", ""))
        message_id = str(event.get("message_id", ""))

        if not account_id or not chat_id or not message_id:
            logger.warning(
                "TelegramNormalizer: missing account_id/chat_id/message_id in event; skipping."
            )
            return []

        # --- Sender ---
        sender_id, sender_name = self._sender_resolver.resolve(event)

        # --- Timestamp ---
        timestamp = self._parse_timestamp(event.get("timestamp"))
        if timestamp is None:
            logger.warning(
                "TelegramNormalizer: missing or unparseable timestamp for msg=%s; skipping.",
                message_id,
            )
            return []

        # --- Lifecycle flags ---
        is_edited = bool(event.get("is_edited", False))
        is_deleted = bool(event.get("is_deleted", False))

        # --- Reply / forward ---
        reply_to = event.get("reply_to_message_id")
        forwarded_from = event.get("forwarded_from")

        # --- Text ---
        raw_text: str | None = event.get("text") or None
        if raw_text:
            raw_text = raw_text.strip() or None

        # --- Attachment ---
        attachment: dict | None = event.get("attachment")
        mime_type: str | None = None
        filename: str | None = None
        file_id: str | None = None
        if attachment and isinstance(attachment, dict):
            mime_type = attachment.get("mime_type")
            filename = attachment.get("filename")
            file_id = attachment.get("file_id")

        # --- Content type ---
        telegram_msg_type = str(event.get("message_type", "text"))
        content_type = self._content_type_mapper.map(telegram_msg_type, mime_type)

        # --- Detect link in text ---
        if content_type == "text" and raw_text and (
            "http://" in raw_text or "https://" in raw_text
        ):
            content_type = "link"

        # --- Build base kwargs ---
        base_kwargs = dict(
            owner_id=owner_id,
            source="telegram",
            source_account_id=account_id,
            conversation_id=chat_id,
            sender_id=sender_id,
            sender_name=sender_name,
            timestamp=timestamp,
            reply_to_message_id=str(reply_to) if reply_to else None,
            forwarded_from=str(forwarded_from) if forwarded_from else None,
            is_edited=is_edited,
            is_deleted=is_deleted,
            indexing_enabled_at=indexing_enabled_at,
            metadata={
                "telegram_account_id": account_id,
                "telegram_chat_id": chat_id,
                "telegram_message_id": message_id,
            },
        )

        objects: list[KnowledgeObject] = []

        # --- Text / link object ---
        if raw_text and not is_deleted:
            text_type = content_type if not attachment else (
                "link" if ("http://" in raw_text or "https://" in raw_text) else "text"
            )
            objects.append(KnowledgeObject(
                source_message_id=message_id,
                content_type=text_type,
                text=raw_text,
                **base_kwargs,
            ))

        # --- Attachment object ---
        if attachment and file_id and not is_deleted:
            attach_content_type = self._content_type_mapper.map(telegram_msg_type, mime_type)
            # Attachment object has no text body (caption already in text object)
            objects.append(KnowledgeObject(
                source_message_id=f"{message_id}:attachment",
                content_type=attach_content_type,
                text=None,
                filename=filename,
                mime_type=mime_type,
                metadata={
                    **base_kwargs["metadata"],
                    "telegram_file_id": file_id,
                    "original_message_id": message_id,
                },
                **{k: v for k, v in base_kwargs.items() if k != "metadata"},
            ))

        # --- Deleted message: emit a single tombstone object ---
        if is_deleted and not objects:
            objects.append(KnowledgeObject(
                source_message_id=message_id,
                content_type="system",
                text=None,
                **base_kwargs,
            ))

        logger.debug(
            "TelegramNormalizer: msg=%s → %d KnowledgeObject(s) (types=%s)",
            message_id,
            len(objects),
            [o.content_type for o in objects],
        )
        return objects

    @staticmethod
    def _parse_timestamp(raw: Any) -> datetime | None:
        """
        Parse an ISO-8601 timestamp string to a timezone-aware datetime.

        Returns None when the input is missing or unparseable.
        """
        if not raw:
            return None
        if isinstance(raw, datetime):
            if raw.tzinfo is None:
                return raw.replace(tzinfo=timezone.utc)
            return raw
        try:
            # Python 3.11+ handles ±HH:MM offsets natively
            dt = datetime.fromisoformat(str(raw))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            return None
