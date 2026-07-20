"""
app/integrations/telegram/services/replacement_builder.py

[ADDITIVE] Pure replacement content planning for all Telegram content types.

Decision Record DR-M2 (Phase 5 — Version NOT in Vector ID):
  Vector ID format: telegram:{account}:{conv}:{msg}:{content_part}:{chunk_index}
  message_version stored in vector metadata (extra dict) only.
  Reason: stable IDs enable upsert-in-place for reused chunks (Strategy C efficiency).
  Rollback: no schema change needed; metadata field is additive.

This builder produces a PreparedMessageReplacement without writing to DB or
ChromaDB. It is a pure function — same inputs → same outputs (deterministic).

Content-type chunk generation strategy (mock / stub implementations):
  text/link → one text:0 chunk with full message text
  pdf       → N page chunks (pdf:0..N-1), each with page_number metadata
  docx      → N section chunks (docx:0..N-1)
  pptx      → N slide chunks (pptx:0..N-1), each with slide_number metadata
  image     → one image:0 chunk combining OCR placeholder + caption
  voice     → N transcript segment chunks (voice:0..N-1), duration metadata
  video     → N transcript/caption chunks (video:0..N-1)
  sticker/document → one chunk per content type

In a production pipeline, PDF/DOCX/PPTX extraction calls real processors.
For the current mock stage, chunk counts are determined by event metadata
(e.g., event.extra_metadata.get("page_count", 1)).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from app.integrations.telegram.services.edit_classifier import EditDecision

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models (Phase 2)
# ---------------------------------------------------------------------------

@dataclass
class PreparedVectorChunk:
    """A single chunk ready for upsert into ChromaDB."""
    vector_id: str
    text: str                          # verbatim text for this chunk
    content_part: str                  # "text", "pdf", "pptx", etc.
    chunk_index: int
    metadata: dict[str, str | int | float | bool]  # scalar-only ChromaDB metadata
    # Specialized positional metadata
    page_number: Optional[int] = None
    slide_number: Optional[int] = None
    transcript_segment: Optional[str] = None
    duration_seconds: Optional[float] = None
    frame_index: Optional[int] = None
    ocr_used: bool = False
    caption_present: bool = False


@dataclass
class PreparedAttachment:
    """Attachment metadata for the replacement message."""
    telegram_file_id: str
    filename: Optional[str]
    mime_type: Optional[str]
    file_size: Optional[int]
    local_path: Optional[str]
    checksum: Optional[str]
    is_reused: bool = False  # True if caption-only edit reused this attachment


@dataclass
class PreparedMessageReplacement:
    """
    Complete replacement plan produced by TelegramReplacementContentBuilder.
    Pure data — no DB or ChromaDB side-effects.
    """
    next_version: int
    message_type: str
    raw_text: Optional[str]
    attachment_records: list[PreparedAttachment]
    chunks: list[PreparedVectorChunk]
    vector_ids: list[str]              # derived from chunks, for convenience
    source_metadata: dict[str, str | int | float | bool]
    is_caption_only_reuse: bool = False


@dataclass
class VectorSetDiff:
    """Result of old-vs-new vector ID set comparison."""
    reused_ids: frozenset[str]
    new_only_ids: frozenset[str]
    stale_ids: frozenset[str]

    @property
    def reused_count(self) -> int: return len(self.reused_ids)
    @property
    def inserted_count(self) -> int: return len(self.new_only_ids)
    @property
    def stale_count(self) -> int: return len(self.stale_ids)


# ---------------------------------------------------------------------------
# Caption-only detection (Phase 10 / DR-M4)
# ---------------------------------------------------------------------------

def is_caption_only_edit(
    old_attachment: Optional[PreparedAttachment],
    new_file_id: Optional[str],
    new_checksum: Optional[str],
) -> bool:
    """
    DR-M4: reuse criteria — both checksum AND telegram_file_id unchanged.

    Returns True only when:
      - An existing attachment is present
      - new_file_id matches old telegram_file_id
      - new_checksum matches old checksum (and both are non-None)

    If checksum matches but file_id differs → re-process (different file).
    If file_id matches but no checksum → re-process (can't confirm).
    """
    if old_attachment is None:
        return False
    if new_file_id != old_attachment.telegram_file_id:
        return False
    if new_checksum is None or old_attachment.checksum is None:
        return False
    return new_checksum == old_attachment.checksum


# ---------------------------------------------------------------------------
# Vector set diffing (Phase 5)
# ---------------------------------------------------------------------------

def compute_vector_set_diff(
    old_vector_ids: list[str],
    new_vector_ids: list[str],
) -> VectorSetDiff:
    """
    Compute reused, new-only, and stale vector ID sets.

    reused_ids  = old ∩ new   (upsert in-place — same ID, updated content)
    new_only    = new − old   (insert fresh)
    stale       = old − new   (delete after successful commit)

    DR-M2 applies: IDs are stable across versions (no version in ID),
    so reused IDs represent chunks that kept the same content_part/chunk_index.
    """
    old_set = frozenset(old_vector_ids)
    new_set = frozenset(new_vector_ids)
    return VectorSetDiff(
        reused_ids=old_set & new_set,
        new_only_ids=new_set - old_set,
        stale_ids=old_set - new_set,
    )


# ---------------------------------------------------------------------------
# Stable vector ID generation (DR-M2)
# ---------------------------------------------------------------------------

def make_vector_id(
    source_account_id: str,
    conversation_id: str,
    source_message_id: str,
    content_part: str,
    chunk_index: int,
) -> str:
    """
    telegram:{account}:{conv}:{msg}:{content_part}:{chunk_index}
    message_version is NOT part of the ID (DR-M2).
    """
    return f"telegram:{source_account_id}:{conversation_id}:{source_message_id}:{content_part}:{chunk_index}"


# ---------------------------------------------------------------------------
# Replacement content builder (Phases 2–5)
# ---------------------------------------------------------------------------

class TelegramReplacementContentBuilder:
    """
    Pure planning service: given an edit event + current message state,
    produces a PreparedMessageReplacement with all replacement chunks.

    No DB writes. No ChromaDB writes. Same inputs → same outputs.
    """

    def build(
        self,
        *,
        owner_id: str,
        source_account_id: str,
        conversation_id: str,
        source_message_id: str,
        sender_id: Optional[str],
        sender_name: Optional[str],
        new_content_type: str,
        new_text: Optional[str],
        next_version: int,
        edit_timestamp: Optional[datetime],
        extra_metadata: dict[str, Any],
        current_attachment: Optional[PreparedAttachment] = None,
        # Caption-only: caller passes these when attachment exists
        new_file_id: Optional[str] = None,
        new_checksum: Optional[str] = None,
        # Extracted text from existing media (for caption-only reuse)
        existing_media_text: Optional[str] = None,
    ) -> PreparedMessageReplacement:
        """
        Build a complete replacement plan.

        Args:
            owner_id, source_account_id, conversation_id, source_message_id:
                Stable Telegram source identity.
            new_content_type: The content type after the edit.
            new_text: The new text/caption, if any.
            next_version: The version number to be committed (current + 1).
            edit_timestamp: The Telegram edit_date for this event.
            extra_metadata: Event-level extras (page_count, slide_count, etc.).
            current_attachment: Existing attachment record (for caption-only detection).
            new_file_id, new_checksum: For caption-only reuse check (DR-M4).
            existing_media_text: Pre-extracted media text to reuse (caption-only).

        Returns:
            PreparedMessageReplacement — pure data, no side effects.
        """
        # Base source metadata attached to every chunk
        ts_iso = (
            edit_timestamp.astimezone(timezone.utc).isoformat()
            if edit_timestamp else ""
        )
        base_meta: dict[str, str | int | float | bool] = {
            "owner_id": owner_id,
            "source": "telegram",
            "source_account_id": source_account_id,
            "conversation_id": conversation_id,
            "sender_id": sender_id or "",
            "sender_name": sender_name or "",
            "source_message_id": source_message_id,
            "content_type": new_content_type,
            "timestamp": ts_iso,
            "is_edited": True,
            "is_deleted": False,
            "message_version": next_version,
        }

        # Caption-only check (DR-M4)
        caption_reuse = is_caption_only_edit(current_attachment, new_file_id, new_checksum)

        # Dispatch to content-type-specific chunk generator
        chunks = self._generate_chunks(
            source_account_id=source_account_id,
            conversation_id=conversation_id,
            source_message_id=source_message_id,
            content_type=new_content_type,
            text=new_text,
            extra=extra_metadata,
            base_meta=base_meta,
            caption_reuse=caption_reuse,
            existing_media_text=existing_media_text,
        )

        vector_ids = [c.vector_id for c in chunks]

        # Attachment record for replacement
        att_records: list[PreparedAttachment] = []
        if new_file_id:
            att_records.append(PreparedAttachment(
                telegram_file_id=new_file_id,
                filename=str(extra_metadata.get("filename", "")),
                mime_type=str(extra_metadata.get("mime_type", "")),
                file_size=int(extra_metadata.get("file_size", 0)) or None,
                local_path=None,  # not yet downloaded
                checksum=new_checksum,
                is_reused=caption_reuse,
            ))
        elif current_attachment and caption_reuse:
            # Reuse existing attachment record unchanged
            att_records.append(PreparedAttachment(
                **{k: getattr(current_attachment, k) for k in (
                    "telegram_file_id", "filename", "mime_type",
                    "file_size", "local_path", "checksum"
                )},
                is_reused=True,
            ))

        logger.info(
            "ReplacementBuilder: msg=%r type=%r version=%d chunks=%d caption_reuse=%s",
            source_message_id, new_content_type, next_version, len(chunks), caption_reuse,
        )

        return PreparedMessageReplacement(
            next_version=next_version,
            message_type=new_content_type,
            raw_text=new_text,
            attachment_records=att_records,
            chunks=chunks,
            vector_ids=vector_ids,
            source_metadata=base_meta,
            is_caption_only_reuse=caption_reuse,
        )

    # ------------------------------------------------------------------
    # Content-type-specific chunk generators
    # ------------------------------------------------------------------

    def _generate_chunks(
        self,
        *,
        source_account_id: str,
        conversation_id: str,
        source_message_id: str,
        content_type: str,
        text: Optional[str],
        extra: dict[str, Any],
        base_meta: dict[str, str | int | float | bool],
        caption_reuse: bool,
        existing_media_text: Optional[str],
    ) -> list[PreparedVectorChunk]:
        """Route to the correct per-content-type generator."""
        def _vid(part: str, idx: int) -> str:
            return make_vector_id(source_account_id, conversation_id, source_message_id, part, idx)

        caption = (text or "").strip()

        if content_type in ("text", "link"):
            body = text or ""
            return [PreparedVectorChunk(
                vector_id=_vid("text", 0),
                text=body,
                content_part="text",
                chunk_index=0,
                metadata={**base_meta, "chunk_index": 0},
            )]

        if content_type == "pdf":
            page_count = int(extra.get("page_count", 1))
            chunks = []
            for page in range(page_count):
                page_text = str(extra.get(f"page_{page}_text", f"PDF page {page + 1} content"))
                combined = f"{caption} {page_text}".strip() if caption else page_text
                meta = {**base_meta, "chunk_index": page, "page_number": page + 1}
                chunks.append(PreparedVectorChunk(
                    vector_id=_vid("pdf", page),
                    text=combined,
                    content_part="pdf",
                    chunk_index=page,
                    metadata=meta,
                    page_number=page + 1,
                    caption_present=bool(caption),
                ))
            return chunks

        if content_type == "docx":
            section_count = int(extra.get("section_count", 1))
            chunks = []
            for sec in range(section_count):
                sec_text = str(extra.get(f"section_{sec}_text", f"DOCX section {sec + 1} content"))
                combined = f"{caption} {sec_text}".strip() if caption else sec_text
                meta = {**base_meta, "chunk_index": sec}
                chunks.append(PreparedVectorChunk(
                    vector_id=_vid("docx", sec),
                    text=combined,
                    content_part="docx",
                    chunk_index=sec,
                    metadata=meta,
                ))
            return chunks

        if content_type == "pptx":
            slide_count = int(extra.get("slide_count", 1))
            chunks = []
            for slide in range(slide_count):
                slide_text = str(extra.get(f"slide_{slide}_text", f"PPTX slide {slide + 1} content"))
                combined = f"{caption} {slide_text}".strip() if caption else slide_text
                meta = {**base_meta, "chunk_index": slide, "slide_number": slide + 1}
                chunks.append(PreparedVectorChunk(
                    vector_id=_vid("pptx", slide),
                    text=combined,
                    content_part="pptx",
                    chunk_index=slide,
                    metadata=meta,
                    slide_number=slide + 1,
                    caption_present=bool(caption),
                ))
            return chunks

        if content_type == "image":
            # For caption-only reuse: existing_media_text holds prior OCR result
            ocr_text = (
                existing_media_text
                if caption_reuse and existing_media_text
                else str(extra.get("ocr_text", ""))
            )
            combined = " ".join(filter(None, [caption, ocr_text])).strip()
            meta = {**base_meta, "chunk_index": 0, "ocr_used": bool(ocr_text), "caption_present": bool(caption)}
            return [PreparedVectorChunk(
                vector_id=_vid("image", 0),
                text=combined or f"image:{source_message_id}",
                content_part="image",
                chunk_index=0,
                metadata=meta,
                ocr_used=bool(ocr_text),
                caption_present=bool(caption),
            )]

        if content_type == "voice":
            segment_count = int(extra.get("segment_count", 1))
            duration = float(extra.get("duration_seconds", 0))
            chunks = []
            for seg in range(segment_count):
                seg_text = (
                    existing_media_text.split("\n")[seg]
                    if (caption_reuse and existing_media_text and
                        len(existing_media_text.split("\n")) > seg)
                    else str(extra.get(f"segment_{seg}_text", f"Voice segment {seg + 1}"))
                )
                combined = f"{caption} {seg_text}".strip() if caption else seg_text
                meta = {**base_meta, "chunk_index": seg,
                        "duration_seconds": duration, "transcript_segment": f"seg_{seg}"}
                chunks.append(PreparedVectorChunk(
                    vector_id=_vid("voice", seg),
                    text=combined,
                    content_part="voice",
                    chunk_index=seg,
                    metadata=meta,
                    transcript_segment=f"seg_{seg}",
                    duration_seconds=duration,
                ))
            return chunks

        if content_type == "video":
            segment_count = int(extra.get("segment_count", 1))
            chunks = []
            for seg in range(segment_count):
                seg_text = (
                    existing_media_text.split("\n")[seg]
                    if (caption_reuse and existing_media_text and
                        len(existing_media_text.split("\n")) > seg)
                    else str(extra.get(f"segment_{seg}_text", f"Video segment {seg + 1}"))
                )
                combined = f"{caption} {seg_text}".strip() if caption else seg_text
                meta = {**base_meta, "chunk_index": seg, "transcript_segment": f"seg_{seg}"}
                chunks.append(PreparedVectorChunk(
                    vector_id=_vid("video", seg),
                    text=combined,
                    content_part="video",
                    chunk_index=seg,
                    metadata=meta,
                    transcript_segment=f"seg_{seg}",
                ))
            return chunks

        # Generic fallback: sticker, document, unknown
        body = text or f"{content_type}:{source_message_id}"
        return [PreparedVectorChunk(
            vector_id=_vid(content_type, 0),
            text=body,
            content_part=content_type,
            chunk_index=0,
            metadata={**base_meta, "chunk_index": 0},
        )]
