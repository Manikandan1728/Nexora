# Tasks — Telegram Vector Metadata & Retrieval

Execute in order. Run `python -m pytest --ignore=tests/test_phase2.py
--ignore=tests/test_phase3.py -q` and `cd frontend && npm run typecheck`
after **each numbered task**, not just at the end.

---

- [x] 1. Audit current metadata data-flow

- [x] 2. Create VectorMetadata canonical model
  - [x] 2.1 Create `models/vector_metadata.py` with all Requirement 1 fields
  - [x] 2.2 Implement `to_vector_store_metadata()` with scalar coercion
  - [x] 2.3 Unit test coercion for every field type (datetime, enum, None, str, int, bool)
  - Requirements: 1

- [x] 3. Implement KnowledgeMetadataMapper
  - [x] 3.1 Create `app/integrations/telegram/mapping/knowledge_metadata_mapper.py`
  - [x] 3.2 Map all required KnowledgeObject fields to VectorMetadata
  - [x] 3.3 Map optional Telegram extras from KnowledgeObject.metadata dict
  - [x] 3.4 Unit test mapping for text, link, PDF, DOCX, PPTX, image, voice, video
  - Requirements: 2

- [x] 4. Wire metadata through content processors
  - [x] 4.1 Audit each processor for identity metadata propagation gaps
  - [x] 4.2 Ensure every derived chunk carries owner/source/conversation/sender/message
  - [x] 4.3 Add specialized fields (page_number, slide_number, transcript_segment, etc.)
  - [x] 4.4 Test each content type produces chunks with full identity + specialized fields
  - Requirements: 3

- [x] 5. Implement and wire stable deterministic vector IDs
  - [x] 5.1 Confirm `KnowledgeObject.vector_document_id()` and `TelegramDeduplicationService.vector_id()` already implement the scheme; wire through KnowledgeMetadataMapper
  - [x] 5.2 Test: same event processed twice → same vector ID, zero duplicate vectors
  - Requirements: 4

- [x] 6. Extend metadata filter schema
  - [x] 6.1 Verify installed ChromaDB version and supported `where` syntax
  - [x] 6.2 Add new Telegram filter fields to `app/retrieval/metadata_filter.py` (or create `TelegramMetadataFilter` extending it) while preserving all existing fields
  - [x] 6.3 Add `EffectiveMetadataFilter` dataclass
  - [x] 6.4 Add validation: empty-string rejection, singular/plural conflict, malformed timestamp, unsupported content_type
  - [x] 6.5 Unit test each validation rule
  - Requirements: 5

- [x] 7. Implement QueryScopeBuilder
  - [x] 7.1 Create `app/retrieval/query_scope_builder.py`
  - [x] 7.2 Force `effective.owner_id = authenticated_owner_id` unconditionally
  - [x] 7.3 Validate requested conversation(s) belong to authenticated owner
  - [x] 7.4 Test: client-supplied owner_id is ignored/overridden in all paths
  - Requirements: 6

- [x] 8. Implement ChromaWhereBuilder
  - [x] 8.1 Create `app/retrieval/chroma_where_builder.py`
  - [x] 8.2 Build filter for single-conversation (owner_id + source + conversation_id)
  - [x] 8.3 Build filter for group+sender (adds sender_id constraint)
  - [x] 8.4 Build filter for multi-conversation using verified ChromaDB syntax
  - [x] 8.5 Implement timestamp range filtering with documented fallback if native unreliable
  - [x] 8.6 Unit test filter dict output for every supported scenario
  - Requirements: 7

- [x] 9. Wire private-chat retrieval end to end
  - Update `query_service.py` to use QueryScopeBuilder + ChromaWhereBuilder
  - Test: query for tg_chat_anu_001 returns only Anu's messages
  - Requirements: 8

- [x] 10. Wire group-sender retrieval end to end
  - Test: query for group + sender_id returns only that sender's messages
  - Requirements: 9

- [x] 11. Wire multi-conversation retrieval end to end
  - Test: conversation_ids=[A, B] returns only from A and B
  - Requirements: 10

- [x] 12. Extend RetrievedDocument model
  - Add optional Telegram fields to `models/retrieved_document.py`
  - Confirm no session paths, phone numbers, or auth details are exposed
  - Requirements: 11

- [x] 13. Extend query response schema with sources[]
  - [x] 13.1 Add `TelegramSourceResponse` Pydantic model to `api/schemas/response_models.py`
  - [x] 13.2 Add `sources` array to `QueryResponse`
  - [x] 13.3 Populate sources in `query_service.py` from retrieved document metadata
  - [x] 13.4 Implement dedup-vs-preserve logic for multi-chunk sources
  - Requirements: 12

- [x] 14. Update frontend filter types and search service
  - [x] 14.1 Add conversation_id, sender_id, source, content_type to query filter types in `frontend/src/types/query.ts`
  - [x] 14.2 Add sources[] type to QueryResponse interface
  - [x] 14.3 Never transmit owner_id from frontend
  - Requirements: 13

- [x] 15. Update source cards in SearchPage / ResultCard
  - Render conversation title/type, sender name, timestamp, content type, filename, snippet
  - Hide raw IDs outside debug view
  - Requirements: 14

- [x] 16. Build isolation test fixtures
  - Create `tests/fixtures/telegram/isolation/` with:
    - owner_1_anu_private.json (Anu private chat, distinct fact)
    - owner_1_anu_group.json (Anu in group, distinct fact)
    - owner_1_arun_private.json (Arun private chat, distinct fact)
    - owner_2_anu_private.json (different owner, same display name "Anu", distinct sender_id)
    - owner_1_pdf_message.json (PDF with full Telegram metadata)
  - Requirements: 15

- [x] 17. Implement end-to-end isolation tests against real test vector store
  - Create `tests/test_telegram_isolation.py`
  - [x] 17.1 Private-chat isolation
  - [x] 17.2 Cross-contact isolation (Anu vs Arun)
  - [x] 17.3 Group-sender isolation
  - [x] 17.4 Private-vs-group isolation
  - [x] 17.5 Duplicate-display-name isolation (owner_1 Anu vs owner_2 Anu)
  - [x] 17.6 Cross-owner isolation (including spoofed owner_id attempt)
  - [x] 17.7 Source-type isolation (Telegram vs non-Telegram)
  - [x] 17.8 Content-type isolation
  - [x] 17.9 Multi-conversation retrieval
  - [x] 17.10 Unknown/unauthorized conversation handling
  - [x] 17.11 Full metadata round-trip (KnowledgeObject → ChromaDB → RetrievedDocument)
  - [x] 17.12 Stable vector ID dedup on reprocess
  - Requirements: 16

- [x] 18. Run backwards-compatibility checks
  - Confirm existing upload workflow, query schema, retrieved-document fields intact
  - Run full suite; compare against baseline (523 passed / 2 known failures / 87 Telegram)
  - Requirements: 17

- [x] 19. Add typed error classes and wire into API
  - Add to `exceptions/exceptions.py`: UnauthorizedOwnerScope, ConversationNotFound,
    ConversationNotOwned, InvalidSenderFilter, UnsupportedFilterCombination,
    InvalidTimestampFilter, VectorFilterBuildError, MissingMandatoryMetadata
  - Wire into error_handlers.py with safe HTTP responses
  - Test: no sensitive detail in any error response body
  - Requirements: 18

- [x] 20. Add structured logging at pipeline boundaries
  - Log (IDs/counts only): event normalized, metadata mapped, chunk inserted,
    query scope built, filter built, retrieval completed, sources assembled
  - Confirm: no message content, phone numbers, OTPs, or session data in logs
  - Requirements: 19

- [x] 21. Update documentation
  - Update `docs/telegram-rag-flow.md` with new Mermaid diagram
  - Update `docs/telegram-data-model.md` with VectorMetadata contract
  - Update `docs/telegram-security.md` with owner isolation details
  - Create `docs/telegram-filtering.md` (filter schema, ChromaDB limitations)
  - Create `docs/telegram-source-citations.md` (sources[] structure)
  - Requirements: 20

- [x] 22. Final validation and completion report
  - [x] 22.1 Full backend suite + frontend typecheck + frontend build vs baseline
  - [x] 22.2 One real data-flow trace: event → KnowledgeObject → VectorMetadata → ChromaDB → RetrievedDocument → API response source
  - [x] 22.3 Isolation proof output for all fixture scenarios
  - [x] 22.4 API request/response examples: private chat, group sender, multi-conversation, spoofed owner_id
  - [x] 22.5 Explicitly deferred: edit sync, delete sync, encryption, live TDLib, WhatsApp legacy migration
  - Requirements: 0–20 (verification)
