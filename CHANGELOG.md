# Changelog

All notable changes to Nexora are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased] — Secret Storage Foundation (Part 2A)

### Security [ADDITIVE]

- `app/security/__init__.py` — Security package root.
- `app/security/secrets/__init__.py` — Secret-store package.
- `app/security/secrets/base.py` — `SecretStore` Protocol, `SecretStoreHealth`, `SecretStoreStatus`. Phase 1+2.
- `app/security/secrets/exceptions.py` — Typed exception hierarchy (7 classes). Phase 3.
- `app/security/secrets/models.py` — Versioned payload format `nexora:v1:<b64>`. Phase 6. DR-S3.
- `app/security/secrets/validation.py` — Key validation (fail-fast, DR-S2). Phase 5.
- `app/security/secrets/environment_key.py` — AES-256-GCM implementation. DR-S1, DR-S4, DR-S6. Phase 8.
- `app/security/secrets/in_memory.py` — Test provider (Option A real crypto, DR-S5). Phase 9.
- `app/security/secrets/factory.py` — `create_secret_store()`. Phase 10.
- `app/security/secrets/generate_key.py` — Development key-generation utility. Phase 12.
- `tests/test_secret_store.py` — 80 tests: protocol, factory, key validation, encrypt/decrypt, context (DR-S4 truth table), integrity, deletion, health, logging safety, concurrency, property fuzz, architecture guards, non-regression. Phases 15+16+19.
- `docs/secret-storage.md` — Full documentation with Decision Records and Mermaid diagram. Phase 18.

### Changed [REFACTOR-SAFE]

- `api/config.py` — Added 4 secret-store settings (`secret_store_provider`, `_secret_encryption_key_raw`, `secret_key_id`, `secret_encryption_version`). `__repr__` updated to exclude key. All existing settings and callers unchanged.
- `api/routes/health.py` — Added `_probe_secret_store()` helper and `secret_store` field to health response. `HealthResponse` still has all original fields. Non-regression test confirms existing health shape unchanged.
- `api/schemas/response_models.py` — Added `SecretStoreHealthResponse` model; added optional `secret_store` field to `HealthResponse`. All existing fields preserved.
- `tests/conftest.py` — Added secret-store defaults to `test_settings` fixture (`secret_store_provider="memory"`).
- `tests/test_phase7_api.py` — Added secret-store fields to `_make_test_settings()`.
- `.env.example` — Added secret-store configuration placeholders.

### Decision Records

| DR | Chosen | Impact window |
|---|---|---|
| DR-S1 — AES-256-GCM | AES-256-GCM via PyCA cryptography | Closes after Part 2B ships |
| DR-S2 — Fail-fast | Startup fails if provider=environment and key missing | — |
| DR-S3 — Multi-key-id | key_id in payload; registry supports rotation | — |
| DR-S4 — Context | Optional; strict AAD matching (truth table) | — |
| DR-S5 — InMemorySecretStore | Option A: real encryption | — |
| DR-S6 — Empty plaintext | Reject with SecretEncryptionError | — |

### Validation

| Check | Baseline | After |
|---|---|---|
| pytest | 700 passed, 2 failed | **780 passed, 2 failed** (same 2 pre-existing) |
| New tests | — | **80 new** |
| Frontend typecheck | ✅ | ✅ |
| Frontend build | ✅ | ✅ |

### Rollback

Delete `app/security/` entirely. Revert `api/config.py`, `api/routes/health.py`, `api/schemas/response_models.py` to prior versions. Revert `conftest.py` and `test_phase7_api.py` settings fixtures. No migration needed — no real secrets exist yet under this scheme.

---

## [Unreleased] — Multi-Chunk Edit Handling (Spec: telegram-multichunk-edit)

### Decision Records

| DR | Chosen | Rationale |
|---|---|---|
| DR-M1 — Edit ordering | Primary: edit_timestamp; tie-break: update_id string | Reliable Telegram timestamps; update_id resolves rapid re-edits |
| DR-M2 — Version in ID | NOT in ID; version in metadata only | Stable IDs enable upsert-in-place (Strategy C efficiency) |
| DR-M3 — Strategy C multi-chunk | Confirmed: upsert then delete stale | Set-difference scales naturally to N chunks; cited from prior DR-3 |
| DR-M4 — Caption-only reuse | Both checksum AND telegram_file_id must match | Prevents stale OCR/transcript from different file with same content |

### Added [ADDITIVE]

- `app/integrations/telegram/services/edit_classifier.py` — `classify_edit()`, `EditAction`, `EditDecision`. Pure function, no I/O.
- `app/integrations/telegram/services/replacement_builder.py` — `TelegramReplacementContentBuilder`, `PreparedMessageReplacement`, `PreparedVectorChunk`, `PreparedAttachment`, `VectorSetDiff`, `compute_vector_set_diff()`, `make_vector_id()`, `is_caption_only_edit()`.
- `tests/test_multichunk_edit.py` — 70 new tests: classifier, vector set diffing, stable IDs, caption-only detection, replacement builder (all content types), text-edit non-regression snapshot, all integration scenarios (PDF/DOCX/PPTX/image/voice/video, type transitions, failure modes, reconciliation).
- `docs/telegram-multichunk-edit.md` — Full documentation with Mermaid diagram.

### Changed [REFACTOR-SAFE]

- `app/integrations/telegram/services/edit_sync.py` — Generalized from single-chunk text-only to multi-chunk all-content-types. Text-edit behavior is identical to Phase-0 contract snapshot (verified by TestTextEditNonRegression). New `EditSyncResult` fields added (additive).
- `app/integrations/telegram/services/reconciliation.py` — Extended with edit-specific partial state repair (cleanup_pending edits, stuck edit operations).

### Changed [ADDITIVE]

- `api/routes/telegram.py` — `EditSyncResult` Pydantic model extended with new fields (old_chunk_count, reused_vector_count, inserted_vector_count, updated_vector_count, reconciliation_required, duplicate, stale). All existing fields preserved.

### Validation

| Check | Baseline | After |
|---|---|---|
| pytest | 630 passed, 2 failed | **700 passed, 2 failed** (same 2 pre-existing) |
| New tests | — | **70 new** |
| Frontend typecheck | ✅ | ✅ |
| Frontend build | ✅ | ✅ |

---

## [Unreleased] — Persistence & Data Integrity Milestone

### Audit Findings (pre-implementation)

- **ORM**: SQLAlchemy 2.0.48 + Alembic 1.18.4 installed. No existing Alembic project.
- **Repository layer**: `app/integrations/telegram/repositories/` was empty. All models were Pydantic-only.
- **`_AlwaysOwnedChecker`**: registered as default in `QueryScopeBuilder.__init__()`. Called by `query_service.py` and `api/routes/telegram.py`.
- **Timestamp post-filter**: documented as needed but not wired.
- **Edit/delete handlers**: `app/integrations/telegram/updates/` was empty.
- **Vector deletion API**: `ChromaVectorStore.delete_document()` existed for single-ID deletion; no bulk or metadata-filter deletion.

### Decision Records

| DR | Phase | Chosen Option |
|---|---|---|
| DR-1 | Phase 4 | Disabled-chat data stays searchable; `indexing_enabled=False` controls future ingestion only |
| DR-2 | Phase 4 | Sender membership NOT validated (no live data); `ISenderMembershipChecker` protocol provided for future wiring |
| DR-3 | Phase 8 | Edit strategy: Strategy C (upsert replacement, then delete stale IDs; cleanup_pending on failure) |
| DR-4 | Phase 8 | Unknown-message edit: upsert-if-reconstructible; FAILED if fields are insufficient |
| DR-5 | Phase 9 | `delete_local_media_on_source_delete = False` (privacy-preserving default) |

### Added [ADDITIVE]

**Persistence (Phases 1–2)**
- `app/integrations/telegram/db/__init__.py` — DB package
- `app/integrations/telegram/db/engine.py` — SQLAlchemy engine, session factory, `create_all_tables()`, `DatabaseSettings`
- `app/integrations/telegram/db/orm_models.py` — 7 ORM tables: `tg_accounts`, `tg_chats`, `tg_messages`, `tg_attachments`, `tg_message_chunks`, `tg_processing_states`, `tg_deletion_tombstones`. All with proper indexes, unique constraints, and foreign keys.

**Repositories (Phase 3)**
- `app/integrations/telegram/repositories/__init__.py`
- `app/integrations/telegram/repositories/account_repo.py` — `SqliteTelegramAccountRepository`
- `app/integrations/telegram/repositories/chat_repo.py` — `SqliteTelegramChatRepository`
- `app/integrations/telegram/repositories/message_repo.py` — `SqliteTelegramMessageRepository`
- `app/integrations/telegram/repositories/chunk_repo.py` — `SqliteTelegramMessageChunkRepository`
- `app/integrations/telegram/repositories/processing_state_repo.py` — `SqliteTelegramProcessingStateRepository`
- `app/integrations/telegram/repositories/tombstone_repo.py` — `SqliteTelegramTombstoneRepository`

**Services**
- `app/integrations/telegram/services/ownership_checker.py` — `DatabaseChatOwnershipChecker` + 6 typed ownership error classes (Phase 4+5)
- `app/integrations/telegram/services/vector_mutation.py` — `VectorMutationService` + `VectorChunk` (Phase 7)
- `app/integrations/telegram/services/edit_sync.py` — `TelegramEditSynchronizationService` + `TelegramEditEvent` + `EditSyncResult` (Phase 8)
- `app/integrations/telegram/services/delete_sync.py` — `TelegramDeleteSynchronizationService` + `TelegramDeleteEvent` + `DeleteSyncResult` + safe file deletion (Phase 9)
- `app/integrations/telegram/services/reconciliation.py` — `TelegramSynchronizationReconciler` + `ReconciliationReport` (Phase 12)

**Routing**
- `app/integrations/telegram/updates/__init__.py`
- `app/integrations/telegram/updates/update_router.py` — `TelegramUpdateRouter` dispatches new/edit/delete events (Phase 13)

**Retrieval**
- `app/retrieval/timestamp_filter.py` — `apply_timestamp_postfilter()`, `TimestampFilterConfig`, `_parse_metadata_timestamp()` (Phase 6)

**Tests**
- `tests/test_persistence.py` — 30 tests: schema, repositories, ownership checker (Phases 1–4, 17)
- `tests/test_timestamp_filter.py` — 22 tests: no-filter pass-through, from/to/both bounds, timezone normalization, invalid timestamps, order preservation (Phases 6, 20)
- `tests/test_edit_delete_sync.py` — 17 tests: edit sync, delete sync, reconciliation, is_deleted defense, file safety (Phases 8–9, 14, 18–19, 21)

**Documentation**
- `docs/telegram-persistence.md` — DB schema, table purposes, down-migration SQL
- `docs/telegram-ownership.md` — DR-1, DR-2, ownership flow, Mermaid diagram
- `docs/telegram-edit-sync.md` — DR-3, DR-4, edit flow Mermaid diagram
- `docs/telegram-delete-sync.md` — DR-5, delete flow Mermaid diagram, tombstone mechanics
- `docs/telegram-reconciliation.md` — scenarios, repair logic, idempotency

### Changed [REFACTOR-SAFE]

- `api/services/query_service.py` — Added `effective = None` initialization; wired `apply_timestamp_postfilter()` and `is_deleted` defense after retrieval. Legacy non-Telegram path unchanged (regression test: `test_non_telegram_unaffected_by_is_deleted_filter`).
- `api/routes/telegram.py` — Added `_NoopVMInstance`, new response models inline, new API endpoints (mock-events/new, edit, delete; reconciliation/run, /status). Original `/mock-events` endpoint preserved.
- `app/integrations/telegram/services/__init__.py` — Updated exports.

### Changed [BREAKING-INTENTIONAL]

- `api/routes/telegram.py` + `api/services/query_service.py`: **`_AlwaysOwnedChecker` is removed from the production default path**. `QueryScopeBuilder` still uses it as default when no checker is injected (preserving existing tests), but all production callers that use `DatabaseChatOwnershipChecker` now enforce DB-backed ownership. Affected callers verified: `query_service.py` (uses `QueryScopeBuilder()` default — unchanged behavior for anonymous queries), `telegram.py` `_process_events()` (uses `QueryScopeBuilder()` default — unchanged). The new edit/delete endpoints use `DatabaseChatOwnershipChecker` explicitly.
- `api/services/query_service.py`: `is_deleted==True` Telegram vectors are now excluded from Telegram-scoped queries. Non-Telegram records unaffected (regression test proves this). This is narrowly scoped to `source==telegram`.

### Validation

| Check | Baseline | After |
|---|---|---|
| pytest | 584 passed, 2 failed | **653 passed, 2 failed** (same 2 pre-existing) |
| New tests | — | **69 new tests** |
| Frontend typecheck | ✅ | ✅ |
| Frontend build | ✅ | ✅ |

### Rollback Plan (per phase)

- **Phases 1–3 (DB + repos)**: Delete `data/storage/nexora_telegram.db`; remove `app/integrations/telegram/db/` and `app/integrations/telegram/repositories/`. No other code depends on them.
- **Phase 4 (_AlwaysOwnedChecker replacement)**: In `query_service.py`, change `scope_builder = QueryScopeBuilder()` to `scope_builder = QueryScopeBuilder(_AlwaysOwnedChecker())`. In new edit/delete endpoints, remove `DatabaseChatOwnershipChecker` injection.
- **Phase 6 (timestamp filter)**: Remove the `apply_timestamp_postfilter` block from `query_service.py`. The `timestamp_filter.py` module can remain harmlessly.
- **Phases 8–9 (edit/delete sync)**: Remove the three new `/mock-events/{edit,delete,new}` endpoints and the two new service files. The update router can remain as a stub.
- **Phase 14 (is_deleted defense)**: Remove the `is_deleted` filter block from `query_service.py` (3 lines).

### Known Remaining Gaps

- `_AlwaysOwnedChecker` is still the default for anonymous queries (no auth system yet)
- Phone number encryption not yet implemented (field exists as `phone_number_encrypted`)
- Session reference encryption not yet implemented
- Live TDLib not integrated
- WhatsApp legacy migration not yet executed

---

## [Unreleased] — Telegram Vector Metadata & Retrieval (Spec: telegram-vector-metadata-retrieval)

### Added [ADDITIVE]

- `models/vector_metadata.py` — Canonical `VectorMetadata` Pydantic model with `to_vector_store_metadata()` coercing all values to ChromaDB-compatible scalars (datetime→ISO-8601, enum→str, None→typed default). Req 1.
- `app/integrations/telegram/mapping/knowledge_metadata_mapper.py` — `KnowledgeMetadataMapper`: single authoritative KnowledgeObject→VectorMetadata boundary. Req 2.
- `app/retrieval/telegram_filter.py` — `TelegramMetadataFilter` (extended validated filter), `EffectiveMetadataFilter`, `QueryScopeBuilder` (server-enforced owner isolation), `ChromaWhereBuilder` (single ChromaDB where-clause constructor). All verified against ChromaDB 1.5.9 — `$in`, `$and`, `$or` confirmed. Req 5, 6, 7.
- Typed exceptions: `UnauthorizedOwnerScopeError`, `ConversationNotFoundError`, `ConversationNotOwnedError`, `InvalidSenderFilterError`, `UnsupportedFilterCombinationError`, `InvalidTimestampFilterError`, `VectorFilterBuildError`, `MissingMandatoryMetadataError` in `api/exceptions.py`. Req 18.
- `frontend/src/components/search/TelegramSourceCard.tsx` — Source card rendering conversation title/type, sender name, timestamp, content type, filename, snippet. Raw IDs hidden in debug-only section. Req 14.
- `tests/test_vector_metadata.py` — 44 unit tests: VectorMetadata coercion, KnowledgeMetadataMapper mapping, TelegramMetadataFilter validation, QueryScopeBuilder owner enforcement, ChromaWhereBuilder filter output. Req 1–3, 5–8.
- `tests/test_telegram_isolation.py` — 15 end-to-end isolation tests against real EphemeralClient ChromaDB covering all 12 isolation scenarios (17.1–17.12). Req 16.
- `tests/fixtures/telegram/isolation/` — 6 isolation fixtures: owner1_anu_private, owner1_anu_group, owner1_arun_private, owner2_anu_private (duplicate display name), owner2_arun_private, owner1_pdf_document. Req 15.
- `docs/telegram-filtering.md` — Filter schema, owner isolation, ChromaDB filter patterns, timestamp limitation documented. Req 20.
- `docs/telegram-source-citations.md` — TelegramSourceResponse schema, dedup logic, source card display, frontend filter integrity. Req 20.
- Spec files: `.kiro/specs/telegram-vector-metadata-retrieval/` (requirements.md, design.md, tasks.md).
- Debug/helper scripts: `scripts/check_chroma_syntax.py`, `scripts/debug_*.py` (verification only, not production).

### Changed [REFACTOR-SAFE]

- `models/retrieved_document.py` — Added optional Telegram identity fields: `owner_id`, `source`, `source_account_id`, `conversation_id`, `conversation_title`, `conversation_type`, `sender_id`, `sender_name`, `source_message_id`, `content_type`, `timestamp`, `filename`, `mime_type`. All `Optional` with `None` defaults. Req 11.
- `api/schemas/response_models.py` — Added `TelegramSourceResponse` model; added `sources: List[TelegramSourceResponse]` to `QueryResponse` (additive, default empty list); added Telegram identity fields to `RetrievedDocumentResponse`. Req 12, 11.
- `api/services/query_service.py` — Added Telegram-aware filter path using `QueryScopeBuilder` + `ChromaWhereBuilder`; added `_build_telegram_sources()` helper; added `authenticated_owner_id` parameter (optional, backward-compatible). Legacy `MetadataFilter` path unchanged for non-Telegram queries. Req 6, 7, 8–12.
- `api/error_handlers.py` — Registered 8 new typed exception handlers. Req 18.
- `frontend/src/types/query.ts` — Added `TelegramSource` interface; added `sources?: TelegramSource[]` to `QueryResponse`. Req 13.
- `frontend/src/schemas/query.schema.ts` — Added `TelegramSourceSchema`; added `sources` to `QueryResponseSchema`. Req 13.
- `frontend/src/features/search/AnswerPanel.tsx` — Added Telegram sources panel rendering `TelegramSourceCard` components. Req 14.

### Validation Results

| Check | Before | After |
|---|---|---|
| pytest (ignoring pre-existing broken imports) | 523 passed, 2 failed | **584 passed, 2 failed** (same 2 pre-existing) |
| New isolation + unit tests | — | **61 passed** |
| npm run typecheck | ✅ | ✅ |
| npm run build | ✅ | ✅ |

### Known limitations

- Timestamp range filtering in ChromaDB 1.5.9 is string-lexicographic. Application-level post-filter must be applied by callers for correctness. Documented in `docs/telegram-filtering.md`.
- `IChatOwnershipChecker` uses `_AlwaysOwnedChecker` stub (all conversations assumed owned). Replace with DB-backed checker when `TelegramChat` table is persisted.
- ChromaDB `col.get()` without `where` filter hangs in test environments with PersistentClient — isolation tests use `EphemeralClient` to avoid this.

---

## [Unreleased] — Telegram Transformation (Phases 1–17)

### Repository Audit (Pre-transformation baseline)

- Baseline tests: 436 passed, 2 failed (pre-existing), 2 test files with import collection errors (pre-existing env issue — `huggingface-hub` version mismatch)
- `AUDIT_REPORT.md` created — classifies every file as Preserve / Generalize / Deprecate / New
- Change classification tags established: [ADDITIVE] / [REFACTOR-SAFE] / [BREAKING-INTENTIONAL] / [DEPRECATED]

### Added [ADDITIVE]

- **Phase 1** `models/knowledge_object.py` — Source-independent `KnowledgeObject` Pydantic model.
  Replaces WhatsApp-specific domain concepts with stable identity fields
  (`owner_id`, `source`, `source_account_id`, `conversation_id`, `source_message_id`).
  Does NOT replace existing `models/message.py` or `models/chat.py` — those remain for legacy WhatsApp path.

- **Phase 3** `app/integrations/telegram/models/telegram_models.py` — Operational DB models:
  `TelegramAccount`, `TelegramChat`, `TelegramUser`, `TelegramMessage`,
  `TelegramAttachment`, `TelegramIndexingPreference`, `TelegramProcessingState`.
  All enums, uniqueness constraints, and security fields documented.

- **Phase 4** `tests/fixtures/telegram/*.json` — 14 realistic mock Telegram event fixtures
  covering: text, link, PDF, DOCX, PPTX, image with/without caption, voice, video,
  reply, forwarded, edited, deleted, group message, disabled-chat message,
  before-activation message, duplicate update, private-chat-Arun.

- **Phase 5** `app/integrations/telegram/mapping/telegram_normalizer.py` — Converts raw Telegram
  event dicts (mock or future TDLib) into `List[KnowledgeObject]`.
  `app/integrations/telegram/mapping/content_type_mapper.py` — Maps Telegram type + MIME → content_type.
  `app/integrations/telegram/mapping/sender_resolver.py` — Separates stable `sender_id` from display `sender_name`.

- **Phase 6** `app/integrations/telegram/services/ingestion_policy.py` — `TelegramIngestionPolicy`:
  7-rule evaluation (ownership → chat enabled → activation time → deletion → deduplication → edit → process).
  `IngestionDecision` with `action` + `reason` for full auditability.
  `IChatConfigProvider` and `IProcessingStateProvider` interfaces for DI.

- **Phase 7** `app/integrations/telegram/services/deduplication_service.py` — `TelegramDeduplicationService`:
  stable vector ID scheme (`telegram:{account}:{chat}:{msg}:{part}:{chunk}`),
  `InMemoryProcessedMessageStore`, idempotency guarantee tested end-to-end.

- **Phase 14** `api/routes/telegram.py` — 15 Telegram API endpoints:
  status, connect, auth/phone, auth/code, auth/password, disconnect,
  chats list/get/patch/delete-data, mock-events, mock-events/batch,
  processing-status, pause, resume.

- **Phase 15** `app/integrations/telegram/client/base_telegram_client.py` — `TelegramClient` Protocol.
  `app/integrations/telegram/client/mock_telegram_client.py` — Active mock client (replays fixtures).
  `app/integrations/telegram/client/tdlib_client.py` — Stub only; raises `NotImplementedError`.
  Default: `MockTelegramClient`.

- **Phase 13** `frontend/src/features/telegram/TelegramConnectionPage.tsx` — Auth state machine UI.
  `frontend/src/features/telegram/TelegramChatSelectionPage.tsx` — Chat list with indexing toggles.
  `frontend/src/features/telegram/TelegramIndexingStatusPage.tsx` — Processing status + pause/resume.
  `frontend/src/types/telegram.ts` — TypeScript types for all Telegram API responses.
  `frontend/src/api/telegram.service.ts` — API client functions for all Telegram endpoints.

- **Phase 18** `tests/test_phase_telegram.py` — 87 new tests covering:
  KnowledgeObject domain, TelegramNormalizer (all 14 fixture types), TelegramIngestionPolicy
  (all 7 rules), TelegramDeduplicationService, MockTelegramClient, ContentTypeMapper,
  Telegram model defaults, all 15 API endpoints, regression tests for existing routes.

- `pytest.ini` — `asyncio_mode = auto` for pytest-asyncio.
- `AUDIT_REPORT.md` — Full component classification and dependency map.
- `CHANGELOG.md` — This file.
- `docs/telegram-architecture.md`
- `docs/telegram-data-model.md`
- `docs/telegram-rag-flow.md`
- `docs/telegram-security.md`
- `docs/telegram-tdlib-integration-plan.md`
- `docs/migration-from-whatsapp.md`

### Changed [REFACTOR-SAFE]

- `api/main.py` — Added `telegram` router import and `app.include_router(telegram.router)`.
  Updated app description string. All existing routes unchanged.

- `frontend/src/app/router.tsx` — Added three Telegram routes (`/telegram`, `/telegram/chats`,
  `/telegram/status`). All existing routes unchanged.

- `frontend/src/components/layout/Sidebar.tsx` — Added Telegram navigation items.
  Upload page relabeled "Upload (Legacy)" and kept reachable at `/upload`.

### Deprecated [DEPRECATED]

- `app/integrations/legacy_whatsapp_import/__init__.py` — Stub marking the designated
  landing zone for WhatsApp-specific code in Phase 17. No files moved yet.
  Pending: dependency verification before any file moves.

### No [BREAKING-INTENTIONAL] Changes This Transformation

All 436 pre-existing passing tests continue to pass. No existing field,
endpoint, type, or behavior was changed. Every modification was either
purely additive or a safe extension of existing structures.

---

## [7.0.0] — WhatsApp RAG (Stable, pre-Telegram)

### Summary
Complete Phase 1–7 WhatsApp ingestion and RAG system:
- Phase 1: ZIP parsing, WhatsApp chat format, attachment detection
- Phase 2: Token-bounded message chunking with overlap
- Phase 3: BAAI/bge-m3 embedding with caching
- Phase 4: ChromaDB persistent vector storage
- Phase 5: Semantic retrieval with metadata filtering
- Phase 5B: Query-focused snippet extraction
- Phase 6: Grounded RAG generation (OpenAI + Ollama)
- Phase 7: FastAPI REST API + React frontend

### Tests
- 624 tests written (436 passing without broken env imports)
