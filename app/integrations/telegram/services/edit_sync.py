"""
app/integrations/telegram/services/edit_sync.py

[REFACTOR-SAFE] Generalized Telegram edit synchronization service.

Generalizes from single-chunk text-only (prior milestone) to full multi-chunk
support for all content types. The text-edit path is one case of the general
mechanism — Phase-0 contract snapshot behavior is preserved exactly.

Strategy: DR-3 / DR-M3 — Strategy C confirmed for multi-chunk.
  Upsert replacement vectors → commit DB version → delete stale vectors.
  If stale deletion fails → cleanup_pending = True.

Edit ordering: DR-M1 — primary signals are edit_timestamp + update_id.

Vector IDs: DR-M2 — message_version NOT in ID, stable content-part:chunk-index format.

Unknown-message edit: DR-4 (prior milestone) — upsert-if-reconstructible.
  For multimodal: "reconstructible" requires complete current message content;
  for media types without full attachment data, falls back to reconciliation-needed.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.integrations.telegram.db.orm_models import (
    TelegramMessageORM, TelegramMessageChunkORM, TelegramProcessingStateORM,
)
from app.integrations.telegram.services.edit_classifier import (
    EditAction, classify_edit,
)
from app.integrations.telegram.services.replacement_builder import (
    TelegramReplacementContentBuilder,
    compute_vector_set_diff,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event model
# ---------------------------------------------------------------------------

@dataclass
class TelegramEditEvent:
    owner_id: str
    source_account_id: str
    conversation_id: str
    source_message_id: str
    new_text: Optional[str]
    new_content_type: str = "text"
    edit_timestamp: Optional[datetime] = None
    update_id: Optional[str] = None
    # For attachment edits
    new_file_id: Optional[str] = None
    new_checksum: Optional[str] = None
    # Extra content metadata (page_count, slide_count, ocr_text, etc.)
    extra_metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Result model (Phase 16 — extended, all existing fields preserved)
# ---------------------------------------------------------------------------

@dataclass
class EditSyncResult:
    # --- Core fields (pre-existing, unchanged) ---
    status: str                      # "ok" | "skipped" | "failed" | "cleanup_pending"
    message_id: str
    previous_version: Optional[int]
    current_version: int
    replacement_vector_count: int    # total replacement chunks
    deleted_vector_count: int
    cleanup_pending: bool
    reason: str = ""

    # --- New fields [ADDITIVE] ---
    old_chunk_count: int = 0
    reused_vector_count: int = 0
    inserted_vector_count: int = 0
    updated_vector_count: int = 0    # == reused (upsert-in-place)
    reconciliation_required: bool = False
    duplicate: bool = False
    stale: bool = False


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class TelegramEditSynchronizationService:
    """
    Synchronizes an edited Telegram message into the database and ChromaDB.

    [REFACTOR-SAFE] generalization of the prior text-only implementation:
    - Text edits produce the same result as before (Phase-0 snapshot).
    - All other content types now produce N chunks using the replacement builder.
    - Vector set diffing (reused/new/stale) replaces the hardcoded text:0 logic.
    """

    def __init__(
        self,
        session: Session,
        vector_mutation,
        message_repo,
        chunk_repo,
        processing_state_repo,
        tombstone_repo,
    ) -> None:
        self._session = session
        self._vm = vector_mutation
        self._msg_repo = message_repo
        self._chunk_repo = chunk_repo
        self._ps_repo = processing_state_repo
        self._tomb_repo = tombstone_repo
        self._builder = TelegramReplacementContentBuilder()

    def synchronize(self, event: TelegramEditEvent) -> EditSyncResult:
        """
        Process an edit event end-to-end. Never raises — errors captured in result.

        Phase-0 contract snapshot preserved for text edits:
          - Vector ID: telegram:{acc}:{conv}:{msg}:text:0
          - Version: prev + 1
          - replacement_vector_count: 1
          - status: "ok" or "cleanup_pending"
        """
        idempotency_key = (
            f"telegram:edit:{event.source_account_id}:"
            f"{event.conversation_id}:{event.source_message_id}:"
            f"{event.update_id or (event.edit_timestamp.isoformat() if event.edit_timestamp else 'unknown')}"
        )

        # --- Load current message state ---
        msg = self._msg_repo.get_by_source_identity(
            self._session,
            event.source_account_id,
            event.conversation_id,
            event.source_message_id,
        )
        tombstone_exists = self._tomb_repo.exists(
            self._session,
            event.source_account_id,
            event.conversation_id,
            event.source_message_id,
        )
        existing_ps = self._ps_repo.get_by_idempotency_key(self._session, idempotency_key)

        # --- Classify the edit (DR-M1) ---
        decision = classify_edit(
            tombstone_exists=tombstone_exists,
            idempotency_key_completed=(existing_ps is not None and existing_ps.status == "completed"),
            message_exists=(msg is not None),
            current_version=msg.current_version if msg else None,
            current_edit_timestamp=msg.updated_at if msg else None,
            incoming_edit_timestamp=event.edit_timestamp,
            incoming_update_id=event.update_id,
            current_update_id=getattr(msg, "last_error_code", None),  # reuse field as update_id store
        )

        if decision.action == EditAction.DUPLICATE:
            return EditSyncResult(
                status="skipped", message_id=event.source_message_id,
                previous_version=None, current_version=0,
                replacement_vector_count=0, deleted_vector_count=0,
                cleanup_pending=False, reason="already_processed",
                duplicate=True,
            )

        if decision.action == EditAction.DELETED:
            return EditSyncResult(
                status="skipped", message_id=event.source_message_id,
                previous_version=None, current_version=0,
                replacement_vector_count=0, deleted_vector_count=0,
                cleanup_pending=False, reason="tombstone_exists",
            )

        if decision.action == EditAction.STALE:
            return EditSyncResult(
                status="skipped", message_id=event.source_message_id,
                previous_version=msg.current_version if msg else None,
                current_version=msg.current_version if msg else 0,
                replacement_vector_count=0, deleted_vector_count=0,
                cleanup_pending=False, reason=decision.reason,
                stale=True,
            )

        # --- Handle unknown message (DR-4) ---
        if decision.action == EditAction.UNKNOWN_MESSAGE:
            return self._handle_unknown_message_edit(event, idempotency_key)

        # --- APPLY: load old chunks, build replacement ---
        prev_version = msg.current_version
        old_active_chunks = self._chunk_repo.list_active_chunks(self._session, msg.id)
        old_vector_ids = [c.vector_id for c in old_active_chunks]

        # Build replacement plan (pure, no I/O)
        replacement = self._builder.build(
            owner_id=event.owner_id,
            source_account_id=event.source_account_id,
            conversation_id=event.conversation_id,
            source_message_id=event.source_message_id,
            sender_id=msg.sender_id,
            sender_name=msg.sender_name,
            new_content_type=event.new_content_type,
            new_text=event.new_text,
            next_version=prev_version + 1,
            edit_timestamp=event.edit_timestamp,
            extra_metadata=event.extra_metadata,
            new_file_id=event.new_file_id,
            new_checksum=event.new_checksum,
        )

        new_vector_ids = replacement.vector_ids
        diff = compute_vector_set_diff(old_vector_ids, new_vector_ids)

        # --- Create processing state ---
        ps = TelegramProcessingStateORM(
            id=str(uuid.uuid4()),
            telegram_message_record_id=msg.id,
            operation_type="edit",
            status="processing",
            idempotency_key=idempotency_key,
            started_at=datetime.now(tz=timezone.utc),
        )
        if not existing_ps:
            self._session.add(ps)
            self._session.flush()
        else:
            ps = existing_ps

        # --- Upsert replacement vectors (Strategy C: write before commit) ---
        try:
            vm_chunks = self._to_vm_chunks(replacement.chunks, diff=diff)
            if vm_chunks:
                self._vm.upsert_chunks(vm_chunks)
            logger.info(
                "EditSync: upserted %d replacement vectors for msg=%r (reused=%d new=%d)",
                len(vm_chunks), event.source_message_id,
                diff.reused_count, diff.inserted_count,
            )
        except Exception as exc:
            logger.warning("EditSync: vector upsert FAILED msg=%r: %s", event.source_message_id, exc)
            ps.status = "failed"
            ps.last_error_code = f"upsert_failed:{str(exc)[:64]}"
            self._session.flush()
            self._session.commit()
            return EditSyncResult(
                status="failed", message_id=event.source_message_id,
                previous_version=prev_version, current_version=prev_version,
                replacement_vector_count=0, deleted_vector_count=0,
                cleanup_pending=False, reason=f"vector_upsert_failed:{exc}",
                reconciliation_required=True,
            )

        # --- DB transaction: version++, activate new chunks, deactivate old ---
        # Deactivate all old active chunks
        self._chunk_repo.deactivate_chunks(self._session, msg.id)

        # Activate new chunk mappings (upsert: reactivate if vector_id exists)
        new_orm_chunks = []
        for chunk in replacement.chunks:
            existing_chunk = self._chunk_repo.get_by_vector_id(self._session, chunk.vector_id)
            if existing_chunk:
                # Reactivate existing chunk (reused vector ID — Strategy C upsert)
                existing_chunk.is_active = True
                existing_chunk.message_version = replacement.next_version
                existing_chunk.content_part = chunk.content_part
                existing_chunk.chunk_index = chunk.chunk_index
                existing_chunk.page_number = chunk.page_number
                existing_chunk.slide_number = chunk.slide_number
                existing_chunk.transcript_segment = chunk.transcript_segment
                self._session.flush()
                new_orm_chunks.append(existing_chunk)
            else:
                orm_chunk = TelegramMessageChunkORM(
                    id=str(uuid.uuid4()),
                    telegram_message_record_id=msg.id,
                    vector_id=chunk.vector_id,
                    content_part=chunk.content_part,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    slide_number=chunk.slide_number,
                    transcript_segment=chunk.transcript_segment,
                    is_active=True,
                    message_version=replacement.next_version,
                )
                self._session.add(orm_chunk)
                new_orm_chunks.append(orm_chunk)
        self._session.flush()

        # Update message record
        self._msg_repo.mark_edited(self._session, msg, event.new_text)
        msg.message_type = event.new_content_type
        self._session.flush()

        # --- Delete stale vectors ---
        stale_ids = list(diff.stale_ids)
        deleted_count = 0
        cleanup_pending = False
        try:
            if stale_ids:
                deleted_count = self._vm.delete_by_vector_ids(stale_ids)
                logger.info(
                    "EditSync: deleted %d stale vectors for msg=%r",
                    deleted_count, event.source_message_id,
                )
        except Exception as exc:
            logger.warning("EditSync: stale deletion FAILED msg=%r: %s", event.source_message_id, exc)
            cleanup_pending = True
            msg.last_error_code = f"stale_delete_failed:{str(exc)[:64]}"
            self._session.flush()

        msg.processing_status = "completed" if not cleanup_pending else "cleanup_pending"
        self._session.flush()

        self._ps_repo.mark_completed(self._session, ps)
        self._session.commit()

        logger.info(
            "EditSync: completed msg=%r version=%d→%d chunks=%d stale=%d cleanup_pending=%s",
            event.source_message_id, prev_version, replacement.next_version,
            len(new_orm_chunks), len(stale_ids), cleanup_pending,
        )

        return EditSyncResult(
            status="cleanup_pending" if cleanup_pending else "ok",
            message_id=event.source_message_id,
            previous_version=prev_version,
            current_version=replacement.next_version,
            replacement_vector_count=len(new_orm_chunks),
            deleted_vector_count=deleted_count,
            cleanup_pending=cleanup_pending,
            old_chunk_count=len(old_vector_ids),
            reused_vector_count=diff.reused_count,
            inserted_vector_count=diff.inserted_count,
            updated_vector_count=diff.reused_count,
        )

    # ------------------------------------------------------------------
    # Unknown message edit (DR-4 — preserved from prior milestone)
    # ------------------------------------------------------------------

    def _handle_unknown_message_edit(
        self, event: TelegramEditEvent, idempotency_key: str
    ) -> EditSyncResult:
        """
        DR-4: upsert-if-reconstructible for unknown messages.
        For text: reconstructible if new_text is present.
        For media types: reconstructible only if text + content type present.
        For attachment-only edits without text: mark reconciliation_required.
        """
        # Determine reconstructibility
        is_text_type = event.new_content_type in ("text", "link")
        has_text = bool(event.new_text and event.new_text.strip())
        has_attachment_meta = bool(event.new_file_id or event.extra_metadata)

        reconstructible = has_text or (has_attachment_meta and event.new_content_type in (
            "image", "voice", "video", "pdf", "docx", "pptx", "document"
        ))

        if not reconstructible:
            return EditSyncResult(
                status="failed", message_id=event.source_message_id,
                previous_version=None, current_version=0,
                replacement_vector_count=0, deleted_vector_count=0,
                cleanup_pending=False, reason="unknown_message_unreconstructible",
                reconciliation_required=True,
            )

        # Create new message record
        new_msg = TelegramMessageORM(
            id=str(uuid.uuid4()),
            owner_id=event.owner_id,
            telegram_account_id=event.source_account_id,
            telegram_chat_id=event.conversation_id,
            telegram_message_id=event.source_message_id,
            message_type=event.new_content_type,
            raw_text=event.new_text,
            is_edited=True,
            current_version=1,
            processing_status="pending",
        )
        self._session.add(new_msg)
        self._session.flush()

        # Build + upsert
        replacement = self._builder.build(
            owner_id=event.owner_id,
            source_account_id=event.source_account_id,
            conversation_id=event.conversation_id,
            source_message_id=event.source_message_id,
            sender_id=None,
            sender_name=None,
            new_content_type=event.new_content_type,
            new_text=event.new_text,
            next_version=1,
            edit_timestamp=event.edit_timestamp,
            extra_metadata=event.extra_metadata,
            new_file_id=event.new_file_id,
            new_checksum=event.new_checksum,
        )

        ps = TelegramProcessingStateORM(
            id=str(uuid.uuid4()),
            telegram_message_record_id=new_msg.id,
            operation_type="edit",
            status="processing",
            idempotency_key=idempotency_key,
            started_at=datetime.now(tz=timezone.utc),
        )
        self._session.add(ps)
        self._session.flush()

        try:
            vm_chunks = self._to_vm_chunks(replacement.chunks)
            if vm_chunks:
                self._vm.upsert_chunks(vm_chunks)
        except Exception as exc:
            ps.status = "failed"
            self._session.flush()
            self._session.commit()
            return EditSyncResult(
                status="failed", message_id=event.source_message_id,
                previous_version=None, current_version=0,
                replacement_vector_count=0, deleted_vector_count=0,
                cleanup_pending=False, reason=f"vector_upsert_failed:{exc}",
            )

        for chunk in replacement.chunks:
            orm_chunk = TelegramMessageChunkORM(
                id=str(uuid.uuid4()),
                telegram_message_record_id=new_msg.id,
                vector_id=chunk.vector_id,
                content_part=chunk.content_part,
                chunk_index=chunk.chunk_index,
                is_active=True,
                message_version=1,
            )
            self._session.add(orm_chunk)

        new_msg.processing_status = "completed"
        self._ps_repo.mark_completed(self._session, ps)
        self._session.commit()

        return EditSyncResult(
            status="ok", message_id=event.source_message_id,
            previous_version=None, current_version=1,
            replacement_vector_count=len(replacement.chunks),
            deleted_vector_count=0, cleanup_pending=False,
            inserted_vector_count=len(replacement.chunks),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _to_vm_chunks(self, prepared_chunks, diff=None) -> list:
        """Convert PreparedVectorChunks to VectorChunk objects for VectorMutationService."""
        from app.integrations.telegram.services.vector_mutation import VectorChunk as VC
        from app.vectorization.embedding_model import EmbeddingModel
        
        if not prepared_chunks:
            return []

        # 1. Fetch old chunks for reused IDs to bypass embedding if text is unchanged
        reused_ids = list(diff.reused_ids) if diff else []
        old_chunks_dict = {}
        if reused_ids:
            old_vc_list = self._vm.get_by_vector_ids(reused_ids)
            for vc in old_vc_list:
                old_chunks_dict[vc.vector_id] = vc

        # 2. Identify which chunks need new embeddings
        result_chunks = []
        chunks_to_embed = []
        
        for chunk in prepared_chunks:
            vc = VC(
                vector_id=chunk.vector_id,
                text=chunk.text,
                embedding=[],  # populate later
                metadata=chunk.metadata,
            )
            result_chunks.append(vc)

            needs_embedding = True
            if chunk.vector_id in old_chunks_dict:
                old_vc = old_chunks_dict[chunk.vector_id]
                # Exact text match -> reuse existing embedding
                if old_vc.text == chunk.text and old_vc.embedding:
                    vc.embedding = old_vc.embedding
                    needs_embedding = False
            
            if needs_embedding:
                chunks_to_embed.append(vc)

        # 3. Batch generate embeddings for chunks that need it
        if chunks_to_embed:
            texts = [c.text for c in chunks_to_embed]
            embeddings = EmbeddingModel().embed_batch(texts)
            for c, emb in zip(chunks_to_embed, embeddings):
                c.embedding = emb

        return result_chunks
