"""
models/document.py — Immutable document model for Phase 2.

WHY THIS MODEL EXISTS
---------------------
Embedding models (e.g. BAAI/bge-m3) do not accept Python objects — they
require plain text strings.  A ``Document`` is the bridge between the
structured ``Chat`` object produced by Phase 1 and the embedding pipeline
that will follow in Phase 3.

Each ``Document`` represents a semantically coherent window of conversation
(a *chunk*) and carries enough metadata so that, after retrieval, the
original context can always be reconstructed without touching the raw
export files.

DESIGN DECISIONS
----------------
* ``frozen=True`` makes every instance immutable once created.  Because
  documents are only ever written once and then read many times (during
  embedding, indexing, retrieval), mutability adds no value and can mask
  bugs.
* All collection fields default to empty tuples / frozen mappings so that
  the model is safe to hash and compare.
* No business logic lives here — that belongs in the builder and enricher.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Sentinel for "no timestamp available"
# ---------------------------------------------------------------------------
_MISSING_TIMESTAMP: str = ""


@dataclass(frozen=True)
class Document:
    """
    A single semantic chunk derived from a ``Chat`` object.

    Attributes
    ----------
    id : str
        A globally unique identifier for this document chunk (UUID-4).
        Used as the primary key when stored in a vector database.

    text : str
        The clean, embedding-ready text content of this chunk.
        Format: "Sender: message\\nSender: message\\n..."

    metadata : dict
        Arbitrary key/value metadata produced by the ``MetadataEnricher``.
        Includes statistics such as message count, attachment flags, and
        conversation duration.  Stored as a plain ``dict`` (not frozen)
        because vector stores typically serialise metadata to JSON.

    participants : tuple[str, ...]
        Sorted tuple of display names of every sender whose message
        appears in this chunk.  Immutable so the Document can be hashed.

    attachments : tuple[str, ...]
        Tuple of attachment filenames/references found in this chunk.
        Empty tuple when the chunk contains no attachment messages.

    message_ids : tuple[int, ...]
        Ordered tuple of ``Message.id`` values for every message included
        in this chunk.  Allows exact reconstruction of the original window.

    source_chat : str
        Identifies the originating chat.  Set to the first participant
        pair (e.g. "Alice & Bob") or a custom label from the pipeline.

    chunk_index : int
        Zero-based position of this chunk within the full document sequence
        for the same chat.  Required for ordered retrieval and overlap
        awareness.

    token_count : int
        Exact token count of ``text`` as measured by the BGE-M3 tokenizer.
        Stored here so Phase 3 never needs to re-tokenize for length checks.

    start_timestamp : str
        Timestamp string of the *first* message in this chunk, taken
        directly from ``Message.timestamp``.  Empty string when unavailable.

    end_timestamp : str
        Timestamp string of the *last* message in this chunk.
        Empty string when unavailable.
    """

    id: str
    text: str
    metadata: dict
    participants: tuple
    attachments: tuple
    message_ids: tuple
    source_chat: str
    chunk_index: int
    token_count: int
    start_timestamp: str
    end_timestamp: str

    def __post_init__(self) -> None:
        """Validate field invariants immediately after construction."""
        # --- id ---
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Document.id must be a non-empty string.")

        # --- text ---
        if not isinstance(self.text, str):
            raise TypeError("Document.text must be a str.")
        # text CAN be empty for system-message-only chunks (they carry metadata)

        # --- metadata ---
        if not isinstance(self.metadata, dict):
            raise TypeError("Document.metadata must be a dict.")

        # --- participants ---
        if not isinstance(self.participants, tuple):
            raise TypeError("Document.participants must be a tuple.")

        # --- attachments ---
        if not isinstance(self.attachments, tuple):
            raise TypeError("Document.attachments must be a tuple.")

        # --- message_ids ---
        if not isinstance(self.message_ids, tuple):
            raise TypeError("Document.message_ids must be a tuple.")

        # --- source_chat ---
        if not isinstance(self.source_chat, str):
            raise TypeError("Document.source_chat must be a str.")

        # --- chunk_index ---
        if not isinstance(self.chunk_index, int) or self.chunk_index < 0:
            raise ValueError("Document.chunk_index must be a non-negative integer.")

        # --- token_count ---
        if not isinstance(self.token_count, int) or self.token_count < 0:
            raise ValueError("Document.token_count must be a non-negative integer.")

        # --- timestamps ---
        if not isinstance(self.start_timestamp, str):
            raise TypeError("Document.start_timestamp must be a str.")
        if not isinstance(self.end_timestamp, str):
            raise TypeError("Document.end_timestamp must be a str.")

    # ------------------------------------------------------------------
    # Convenience helpers (read-only; frozen dataclass cannot have setters)
    # ------------------------------------------------------------------

    @property
    def is_empty(self) -> bool:
        """True when the text payload carries no meaningful content."""
        return not self.text.strip()

    @property
    def has_attachments(self) -> bool:
        """True when at least one attachment reference is present."""
        return len(self.attachments) > 0

    def __repr__(self) -> str:
        return (
            f"Document(id={self.id!r}, chunk_index={self.chunk_index}, "
            f"token_count={self.token_count}, "
            f"messages={len(self.message_ids)}, "
            f"participants={self.participants})"
        )


# ---------------------------------------------------------------------------
# Factory helper — keeps construction logic out of the dataclass itself
# ---------------------------------------------------------------------------

def make_document_id() -> str:
    """Returns a fresh UUID-4 string suitable for ``Document.id``."""
    return str(uuid.uuid4())
