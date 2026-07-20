# Requirements — Telegram Multi-Chunk Edit Handling

## Introduction

Nexora's Telegram edit synchronization currently handles only single-chunk text
messages. This spec implements full multi-chunk edit handling covering all
Telegram content types (text, link, PDF, DOCX, PPTX, image, voice, video) with
proper vector set diffing, failure-safe replacement (Strategy C), attachment
lifecycle management, caption-only optimization, and reconciliation repair.

**Baseline to preserve:** 630 tests passed, 2 known pre-existing failures.
No new failures may be introduced.

**Phase-0 Contract Snapshot (text-edit, pre-generalization):**
- Input: TelegramEditEvent with new_text, new_content_type="text"
- Vector ID: `telegram:{account}:{conv}:{msg}:text:0` (exactly one)
- Version: increments by 1
- Replacement count: 1
- Result: EditSyncResult with status "ok" or "cleanup_pending"

---

## Requirement 1 — Edit Version Contract

**User Story:** As the edit sync service, I need one authoritative ordering rule
so that newer edits always replace older content and duplicate/stale events are
safely ignored.

### Acceptance Criteria

- THE SYSTEM SHALL classify each incoming edit as APPLY, DUPLICATE, STALE, DELETED, or UNKNOWN_MESSAGE before any mutation.
- WHEN an incoming edit has the same idempotency key as an already-completed operation THE SYSTEM SHALL return DUPLICATE with no state change.
- WHEN an incoming edit_timestamp is strictly earlier than the stored edit_timestamp AND the update_id does not indicate it is newer THE SYSTEM SHALL return STALE.
- WHEN a deletion tombstone exists THE SYSTEM SHALL return DELETED.
- WHEN a message does not exist in the DB THE SYSTEM SHALL return UNKNOWN_MESSAGE.
- THE SYSTEM SHALL increment message_version exactly once per accepted edit.

---

## Requirement 2 — Multi-Chunk Replacement Planning

**User Story:** As a developer, I want a pure replacement planner that produces
all replacement chunks without mutating any active state.

### Acceptance Criteria

- THE SYSTEM SHALL implement `TelegramReplacementContentBuilder` that returns `PreparedMessageReplacement` without writing to DB or ChromaDB.
- `PreparedMessageReplacement` SHALL contain: next_version, message_type, raw_text, chunks (list of PreparedVectorChunk), vector_ids (list of str), source_metadata.
- WHEN the same event is planned twice THE SYSTEM SHALL produce identical output (deterministic).
- THE SYSTEM SHALL propagate owner_id, source, source_account_id, conversation_id, sender_id, source_message_id to every chunk's metadata.

---

## Requirement 3 — All Content Types

### Acceptance Criteria

- WHEN text is edited THE SYSTEM SHALL produce exactly one text:0 vector.
- WHEN PDF is edited THE SYSTEM SHALL produce one vector per simulated page chunk with page_number metadata.
- WHEN DOCX is edited THE SYSTEM SHALL produce section chunks.
- WHEN PPTX is edited THE SYSTEM SHALL produce slide chunks with slide_number metadata.
- WHEN image is edited THE SYSTEM SHALL produce chunks combining OCR text and caption.
- WHEN voice is edited THE SYSTEM SHALL produce transcript segment chunks.
- WHEN video is edited THE SYSTEM SHALL produce transcript/caption chunks.
- WHEN content type changes (text→PDF, PDF→text, etc.) THE SYSTEM SHALL use the new content_part in vector IDs.

---

## Requirement 4 — Stable Deterministic Vector IDs (DR-5)

### Acceptance Criteria

- THE SYSTEM SHALL use: `telegram:{source_account_id}:{conversation_id}:{source_message_id}:{content_part}:{chunk_index}`
- THE SYSTEM SHALL NOT include message_version in the vector ID.
- message_version SHALL be stored as vector metadata only.
- Retry of the same edit SHALL produce identical vector IDs.

---

## Requirement 5 — Vector Set Diffing

### Acceptance Criteria

- THE SYSTEM SHALL compute reused_ids = old ∩ new, new_only = new − old, stale = old − new.
- THE SYSTEM SHALL upsert all new and reused vectors.
- THE SYSTEM SHALL delete stale vectors after successful DB commit.
- THE SYSTEM SHALL NOT delete a vector ID that is in the replacement set.
- EditSyncResult SHALL include reused_vector_count, inserted_vector_count, deleted_vector_count.

---

## Requirement 6 — Strategy C Multi-Chunk

### Acceptance Criteria

- THE SYSTEM SHALL upsert replacement vectors before any stale deletion.
- THE SYSTEM SHALL commit the DB version increment before stale deletion.
- WHEN stale deletion fails THE SYSTEM SHALL set cleanup_pending=True.
- THE SYSTEM SHALL NOT make partial replacement active if vector upsert fails.

---

## Requirement 7 — Failure Safety

### Acceptance Criteria

- WHEN replacement vector upsert fails THE SYSTEM SHALL NOT increment version and SHALL preserve old searchable state.
- WHEN stale deletion fails THE SYSTEM SHALL keep new version active and set cleanup_pending=True.
- WHEN only some replacement vectors are written THE SYSTEM SHALL record written IDs for reconciliation.

---

## Requirement 8 — Caption-Only Optimization

### Acceptance Criteria

- WHEN caption changes but both checksum AND telegram_file_id are unchanged THE SYSTEM SHALL reuse existing OCR/transcript extraction.
- WHEN checksum matches but telegram_file_id differs THE SYSTEM SHALL re-process.
- WHEN no checksum is available THE SYSTEM SHALL re-process.
- Caption-only edits SHALL regenerate embeddings from new caption + existing media text.
- After caption-only edit THE OLD CAPTION must not be searchable.

---

## Requirement 9 — Reconciliation

### Acceptance Criteria

- THE SYSTEM SHALL detect and repair: replacement written but DB not committed; DB committed but stale remain; old chunks active after edit; partial vector writes.
- Reconciliation SHALL be idempotent.
- Reconciliation SHALL NOT recreate deleted messages.

---

## Requirement 10 — Non-Regression (Phase-0 Snapshot)

### Acceptance Criteria

- WHEN a text edit is processed through the generalized pipeline THE SYSTEM SHALL produce the same vector ID, version increment, and result shape as the pre-generalization path.
- THE SYSTEM SHALL NOT introduce new failures beyond the 2 known pre-existing ones.
- THE SYSTEM SHALL pass frontend typecheck and production build.
