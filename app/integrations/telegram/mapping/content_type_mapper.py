"""
app/integrations/telegram/mapping/content_type_mapper.py

[ADDITIVE] — New file. Maps Telegram message types and MIME types to
Nexora KnowledgeObject content_type strings.
"""

from __future__ import annotations

# Maps Telegram message_type strings to KnowledgeObject content_type
_TELEGRAM_TYPE_MAP: dict[str, str] = {
    "text":       "text",
    "link":       "link",
    "photo":      "image",
    "video":      "video",
    "audio":      "voice",
    "voice":      "voice",
    "document":   "document",   # refined by MIME below
    "sticker":    "sticker",
    "animation":  "video",
    "video_note": "video",
    "contact":    "system",
    "location":   "system",
    "poll":       "system",
    "system":     "system",
    "unknown":    "text",
}

# MIME type → content_type overrides (applied when message_type == "document")
_MIME_TYPE_MAP: dict[str, str] = {
    "application/pdf":                                                                    "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document":           "docx",
    "application/msword":                                                                 "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation":         "pptx",
    "application/vnd.ms-powerpoint":                                                      "pptx",
    "image/jpeg":   "image",
    "image/png":    "image",
    "image/gif":    "image",
    "image/webp":   "image",
    "video/mp4":    "video",
    "video/webm":   "video",
    "audio/ogg":    "voice",
    "audio/mpeg":   "voice",
    "audio/mp4":    "voice",
}


class ContentTypeMapper:
    """
    Maps Telegram-specific message type and MIME type values to
    Nexora KnowledgeObject content_type strings.

    Mapping priority:
    1. If message_type is "document" and mime_type is known → use MIME map
    2. Otherwise → use Telegram type map
    3. Unknown types fall back to "document"
    """

    @staticmethod
    def map(telegram_message_type: str, mime_type: str | None = None) -> str:
        """
        Return the Nexora content_type for a Telegram message.

        Args:
            telegram_message_type: The Telegram message type string.
            mime_type:             MIME type of the attachment, if any.

        Returns:
            A Nexora content_type string (always non-empty).
        """
        msg_type = telegram_message_type.lower() if telegram_message_type else "unknown"

        # For document messages, try to refine via MIME type
        if msg_type == "document" and mime_type:
            mime_lower = mime_type.lower().split(";")[0].strip()
            if mime_lower in _MIME_TYPE_MAP:
                return _MIME_TYPE_MAP[mime_lower]

        return _TELEGRAM_TYPE_MAP.get(msg_type, "document")
