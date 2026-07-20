"""
models/vector_metadata.py — Canonical vector metadata contract for Nexora.

[ADDITIVE] — New file. No existing code is modified.

This is the single authoritative model for all metadata stored alongside
every vector in ChromaDB. Every source must
must produce a VectorMetadata instance before insertion.

WHY THIS MODEL EXISTS
---------------------
ChromaDB metadata must be flat dicts of scalars (str, int, float, bool).
This model enforces the canonical field set, consistent defaults, and
provides to_vector_store_metadata() which coerces all values to
ChromaDB-compatible scalars — including datetime → ISO-8601, enum → str,
None → typed default.

REQUIREMENT COVERAGE
--------------------
Req 1: Canonical field set with consistent defaults.
Req 3: Specialized fields (page_number, slide_number, etc.) in extra dict.
Req 4: chunk_index is part of the stable ID scheme.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class VectorMetadata(BaseModel):
    """
    Canonical metadata stored alongside every vector in ChromaDB.

    All fields have safe defaults so a partially-populated object never
    omits a key inconsistently. to_vector_store_metadata() coerces
    everything to ChromaDB-compatible scalars.

    Fields not covered by the canonical schema (e.g. page_number,
    slide_number, transcript_segment) go in `extra` and are flattened
    into the output dict by to_vector_store_metadata().
    """

    # --- Owner / security (MANDATORY) ---
    owner_id: str
    source: str                       # "telegram"

    # --- Source identity ---
    source_account_id: str = ""
    conversation_id: str = ""
    conversation_title: str = ""
    conversation_type: str = ""       # "private", "group", "channel", etc.

    # --- Sender (retrieval key = sender_id, NOT sender_name) ---
    sender_id: str = ""
    sender_name: str = ""             # display only; never filter on this

    # --- Message identity ---
    source_message_id: str = ""
    content_type: str = "text"        # one of SUPPORTED_CONTENT_TYPES

    # --- Timing ---
    timestamp: datetime | None = None  # serialized to ISO-8601 by coercion

    # --- Attachment ---
    filename: str = ""
    mime_type: str = ""
    attachment_id: str = ""

    # --- Conversation structure ---
    reply_to_message_id: str = ""

    # --- Chunk position ---
    chunk_index: int = 0

    # --- Lifecycle ---
    is_edited: bool = False
    is_deleted: bool = False

    # --- Source-agnostic legacy fields (kept for existing ChromaDB collection compatibility)
    source_chat: str = ""
    start_timestamp: str = ""
    end_timestamp: str = ""
    message_count: int = 0
    token_count: int = 0
    attachment_count: int = 0
    contains_images: bool = False
    contains_audio: bool = False
    contains_video: bool = False
    contains_documents: bool = False
    embedding_model: str = ""
    schema_version: str = ""

    # --- Specialized content fields (page/slide/transcript/etc.) ---
    # These live in extra so the canonical schema stays flat but extensible.
    extra: dict[str, str | int | float | bool] = Field(default_factory=dict)

    model_config = {"frozen": False}

    # ------------------------------------------------------------------
    # Coercion
    # ------------------------------------------------------------------

    def to_vector_store_metadata(self) -> dict[str, str | int | float | bool]:
        """
        Return a flat dict of ChromaDB-compatible scalar values.

        Coercion rules:
        - datetime → ISO-8601 string (UTC or with tzinfo)
        - Enum     → .value (str)
        - None     → "" for str fields, 0 for int fields, False for bool fields
        - bool     → bool (kept as-is; ChromaDB supports bool natively)
        - extra    → merged in at the top level (no nesting)

        Returns:
            Dict[str, str | int | float | bool] ready for ChromaDB insertion.

        Raises:
            ValueError: If a mandatory field (owner_id, source) is empty.
        """
        if not self.owner_id or not self.owner_id.strip():
            raise ValueError("VectorMetadata.owner_id must not be empty.")
        if not self.source or not self.source.strip():
            raise ValueError("VectorMetadata.source must not be empty.")

        result: dict[str, str | int | float | bool] = {
            # Mandatory
            "owner_id":             self.owner_id,
            "source":               self.source,
            # Source identity
            "source_account_id":    self.source_account_id,
            "conversation_id":      self.conversation_id,
            "conversation_title":   self.conversation_title,
            "conversation_type":    self.conversation_type,
            # Sender
            "sender_id":            self.sender_id,
            "sender_name":          self.sender_name,
            # Message identity
            "source_message_id":    self.source_message_id,
            "content_type":         self._coerce_enum_or_str(self.content_type),
            # Timing
            "timestamp":            self._coerce_datetime(self.timestamp),
            # Attachment
            "filename":             self.filename,
            "mime_type":            self.mime_type,
            "attachment_id":        self.attachment_id,
            # Conversation structure
            "reply_to_message_id":  self.reply_to_message_id,
            # Chunk
            "chunk_index":          self.chunk_index,
            # Lifecycle
            "is_edited":            self.is_edited,
            "is_deleted":           self.is_deleted,
            # Legacy compatibility
            "source_chat":          self.source_chat or self.conversation_title or self.conversation_id,
            "start_timestamp":      self.start_timestamp,
            "end_timestamp":        self.end_timestamp,
            "message_count":        self.message_count,
            "token_count":          self.token_count,
            "attachment_count":     self.attachment_count,
            "contains_images":      self.contains_images,
            "contains_audio":       self.contains_audio,
            "contains_video":       self.contains_video,
            "contains_documents":   self.contains_documents,
            "embedding_model":      self.embedding_model,
            "schema_version":       self.schema_version,
        }

        # Merge specialized extra fields (page_number, slide_number, etc.)
        for k, v in self.extra.items():
            coerced = self._coerce_scalar(v)
            if coerced is not None:
                result[k] = coerced

        return result

    # ------------------------------------------------------------------
    # Private coercion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _coerce_datetime(v: datetime | None) -> str:
        """datetime → ISO-8601 string; None → empty string."""
        if v is None:
            return ""
        return v.isoformat()

    @staticmethod
    def _coerce_enum_or_str(v: Any) -> str:
        """Enum → .value; str → str; other → str(v)."""
        if isinstance(v, Enum):
            return str(v.value)
        if v is None:
            return ""
        return str(v)

    @staticmethod
    def _coerce_scalar(v: Any) -> str | int | float | bool | None:
        """
        Coerce an arbitrary value to a ChromaDB-compatible scalar.
        Returns None if the value cannot be safely coerced.
        """
        if isinstance(v, bool):
            return v
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            return v
        if isinstance(v, str):
            return v
        if isinstance(v, Enum):
            return str(v.value)
        if isinstance(v, datetime):
            return v.isoformat()
        if v is None:
            return ""
        # Last resort: stringify
        try:
            return str(v)
        except Exception:
            return None
