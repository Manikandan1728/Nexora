# Requirements — Telegram Vector Metadata & Retrieval

## Introduction

Nexora's Telegram ingestion path already normalizes mock Telegram events into
KnowledgeObject instances and runs them through the existing processing,
chunking, and embedding pipeline into ChromaDB. What is not yet guaranteed is
that Telegram identity metadata (owner, conversation, sender, message) survives
that pipeline intact, and that retrieval can be scoped securely by owner,
conversation, sender, source, and content type.

This spec covers completing that metadata propagation and proving — through real
vector-store-backed tests, not filter-builder unit tests alone — that data never
leaks across contacts, chats, groups, or Nexora users.

Live TDLib integration, message edit/delete synchronization, and encryption are
explicitly out of scope for this spec.

**Baseline to preserve:** 523 backend tests passing, 2 known pre-existing
failures, 87 Telegram-specific tests passing, frontend typecheck passing,
frontend production build passing. No new failures may be introduced.

---

## Requirement 0 — Data-Flow Audit

**User Story:** As an engineer implementing this spec, I want a documented trace
of the current metadata path, so that I extend existing components instead of
duplicating or breaking them.

### Acceptance Criteria

- WHEN the audit is performed THE SYSTEM SHALL document, file-by-file, the
  path: mock Telegram event → normalizer → KnowledgeObject → content processor
  → chunk → embedding request → vector-store insertion → vector-store metadata
  → similarity-search result → retrieved-document model → query service →
  response schema → frontend source card.
- WHEN metadata loss points are found THE SYSTEM SHALL record exactly where and
  why metadata is dropped or transformed.
- WHEN existing filter-building or owner_id-deriving code is found THE SYSTEM
  SHALL record its file location before any new filter-building code is written.
- IF an existing model or service already covers part of this spec THEN THE
  SYSTEM SHALL extend it rather than create a parallel abstraction.
- WHEN the audit is complete THE SYSTEM SHALL list which changes could affect
  legacy non-Telegram ingestion before implementation begins.

---

## Requirement 1 — Canonical Vector Metadata Contract

**User Story:** As a platform maintainer, I want one canonical, typed vector
metadata model, so that every chunk stored in ChromaDB carries a consistent,
traceable set of identity fields regardless of content type.

### Acceptance Criteria

- WHEN a chunk derived from Telegram content is stored THE SYSTEM SHALL include
  owner_id, source, source_account_id, conversation_id, conversation_title,
  conversation_type, sender_id, sender_name, source_message_id, content_type,
  timestamp, filename, mime_type, attachment_id, reply_to_message_id,
  chunk_index, is_edited, is_deleted whenever the corresponding value is
  available.
- WHEN a value is unavailable THE SYSTEM SHALL apply a consistent default
  (empty string, 0, or false) rather than omitting the key inconsistently.
- THE SYSTEM SHALL reject or convert any metadata value that is not a string,
  integer, float, or boolean before writing to ChromaDB.
- WHEN a datetime is stored THE SYSTEM SHALL serialize it as an ISO-8601 string.
- WHEN an enum is stored THE SYSTEM SHALL serialize it as its string value.
- THE SYSTEM SHALL NOT serialize an entire raw Telegram event into vector
  metadata.
- IF an equivalent metadata model already exists in the repository THEN THE
  SYSTEM SHALL extend it instead of introducing a duplicate model.

---

## Requirement 2 — KnowledgeObject-to-VectorMetadata Mapping

**User Story:** As a developer extending Nexora to new sources, I want one
authoritative mapping between KnowledgeObject and vector metadata, so that
downstream chunkers and processors stay source-agnostic.

### Acceptance Criteria

- WHEN a KnowledgeObject is mapped to vector metadata THE SYSTEM SHALL populate
  owner_id, source, source_account_id, conversation_id, sender_id, sender_name,
  source_message_id, content_type, timestamp, filename, mime_type, and
  reply_to_message_id directly from the corresponding KnowledgeObject fields.
- WHEN optional Telegram-specific values (conversation_title, conversation_type,
  attachment_id, is_edited, is_deleted) are present in normalized metadata THE
  SYSTEM SHALL include them.
- THE SYSTEM SHALL implement this mapping in exactly one place, used by all
  content processors.
- THE SYSTEM SHALL NOT make chunking or processing code aware of
  Telegram-specific event formats — only the mapper may know about Telegram's
  shape.

---

## Requirement 3 — Metadata Preservation Through Content Processing

**User Story:** As a user searching my Telegram history, I want file-derived
chunks (PDF, DOCX, PPTX, image, voice, video) to remain traceable to their
original message, so that source citations are accurate for every content type.

### Acceptance Criteria

- WHEN a text, link, PDF, DOCX, PPTX, image, voice, or video message produces
  one or more derived chunks THE SYSTEM SHALL propagate owner_id, source,
  conversation_id, sender_id, and source_message_id to every derived chunk.
- THE SYSTEM SHALL NOT produce a chunk containing only filename, position, and
  text without its parent message's identity fields.
- WHEN a PDF chunk is produced THE SYSTEM SHALL include page_number where known.
- WHEN a PPTX chunk is produced THE SYSTEM SHALL include slide_number where known.
- WHEN a voice chunk is produced THE SYSTEM SHALL include transcript_segment and
  duration_seconds where known.
- WHEN a video chunk is produced THE SYSTEM SHALL include transcript_segment and
  frame_index where known.
- WHEN an image chunk is produced THE SYSTEM SHALL include ocr_used and
  caption_present where known.
- THE SYSTEM SHALL store only scalar-compatible values for all specialized fields.

---

## Requirement 4 — Stable Deterministic Vector Identifiers

**User Story:** As a platform operator, I want vector IDs to be deterministic,
so that retries, restarts, and duplicate Telegram updates never create duplicate
embeddings.

### Acceptance Criteria

- WHEN a Telegram-derived chunk is stored THE SYSTEM SHALL use the ID format
  `telegram:{source_account_id}:{conversation_id}:{source_message_id}:{content_part}:{chunk_index}`.
- WHEN the same mock Telegram event is processed twice THE SYSTEM SHALL produce
  the same vector ID both times and SHALL NOT create a duplicate vector.
- THE SYSTEM SHALL reuse the existing deduplication service rather than
  implementing a second, competing deduplication mechanism.
- THE SYSTEM SHALL generate an ID scheme compatible with future edit-replacement
  and delete-synchronization work.

---

## Requirement 5 — Extended Metadata Filter Schema

**User Story:** As a backend developer, I want one extended, validated filter
schema, so that queries can be scoped by owner, source, conversation(s), sender,
content type(s), message ID, and time range without ad hoc filter dictionaries.

### Acceptance Criteria

- THE SYSTEM SHALL support filter fields: owner_id, source, source_account_id,
  conversation_id, conversation_ids, sender_id, content_type, content_types,
  source_message_id, timestamp_from, timestamp_to, while preserving all
  currently-supported filter fields.
- IF an identifier filter is an empty string WHERE that is semantically invalid
  THEN THE SYSTEM SHALL reject the request.
- IF both a singular and plural form of the same filter are supplied in a way
  not explicitly supported THEN THE SYSTEM SHALL reject the request.
- IF a timestamp filter is malformed THEN THE SYSTEM SHALL reject the request.
- IF a content_type is not among supported types THEN THE SYSTEM SHALL reject
  the request.
- THE SYSTEM SHALL NOT expose an unrestricted, arbitrary ChromaDB where filter
  to the frontend under any circumstance.

---

## Requirement 6 — Server-Enforced Owner Isolation

**User Story:** As a Nexora user, I want the backend — not the client — to
determine whose data I can see, so that no request can retrieve another user's
data.

### Acceptance Criteria

- THE SYSTEM SHALL derive effective owner_id from the authenticated Nexora user
  or existing trusted request context, never from client-supplied input.
- IF a client-supplied owner_id differs from the authenticated owner THEN THE
  SYSTEM SHALL either ignore it or reject the request with an authorization
  error, consistent with existing API conventions.
- WHEN a query requests one or more conversation_id/conversation_ids THE SYSTEM
  SHALL verify each belongs to the authenticated owner before querying, and
  SHALL reject or exclude any that do not.
- THE SYSTEM SHALL NOT pass a client-provided owner_id directly into a ChromaDB
  where filter under any code path.

---

## Requirement 7 — ChromaDB Where-Filter Construction

**User Story:** As a backend developer, I want one controlled filter-builder,
so that every query against ChromaDB is constructed consistently and safely.

### Acceptance Criteria

- THE SYSTEM SHALL build ChromaDB where filters in exactly one component, fed
  only by the server-validated EffectiveMetadataFilter.
- WHEN a single conversation is requested THE SYSTEM SHALL build a filter
  combining owner_id, source, and conversation_id.
- WHEN a sender within a conversation is requested THE SYSTEM SHALL additionally
  constrain by sender_id.
- WHEN multiple conversations are requested THE SYSTEM SHALL use whatever
  multi-value syntax the installed ChromaDB version actually supports, verified
  against the real installed version.
- IF native timestamp range filtering is unreliable in the installed ChromaDB
  version THEN THE SYSTEM SHALL document the limitation, apply the safest
  supported prefilter, and apply a deterministic application-level post-filter.
- THE SYSTEM SHALL NOT claim native range-filtering support that the installed
  ChromaDB version does not actually provide.

---

## Requirement 8 — Private-Chat Retrieval

- WHEN a query specifies source=telegram and a single conversation_id THE SYSTEM
  SHALL return results only from that conversation, for the authenticated owner.
- THE SYSTEM SHALL NOT return results from a different private chat, a group
  containing the same display name, another Nexora user's data, or a different
  contact who happens to share a display name.

---

## Requirement 9 — Group-Sender Retrieval

- WHEN a query specifies a group conversation_id and a sender_id THE SYSTEM
  SHALL return results only from that sender within that group.
- THE SYSTEM SHALL NOT return other group members' messages, the same sender's
  private-chat messages, or another owner's group data.

---

## Requirement 10 — Multi-Conversation Retrieval

- WHEN a query specifies conversation_ids THE SYSTEM SHALL return results only
  from the requested conversations that belong to the authenticated owner.
- IF a requested conversation ID is unauthorized or unknown THEN THE SYSTEM
  SHALL reject it or exclude it.

---

## Requirement 11 — Retrieved Document Model

- THE SYSTEM SHALL extend the retrieved-document model with optional fields:
  owner_id, source, source_account_id, conversation_id, conversation_title,
  conversation_type, sender_id, sender_name, source_message_id, content_type,
  timestamp, filename, mime_type, chunk_index.
- THE SYSTEM SHALL NOT expose internal session paths, local file paths, phone
  numbers, authorization details, or raw Telegram session data through this model.

---

## Requirement 12 — RAG Query Response with Source Citations

- WHEN a RAG answer is generated from Telegram-sourced chunks THE SYSTEM SHALL
  include a sources array with document_id, source, conversation_id,
  conversation_title, conversation_type, sender_id, sender_name, message_id,
  timestamp, content_type, filename, chunk_index, snippet, and score.
- THE SYSTEM SHALL preserve backwards-compatible field names/shapes for existing
  frontend consumers where practical.
- WHEN multiple chunks reference the same source message with no additional value
  THE SYSTEM SHALL deduplicate them; WHEN chunks represent meaningfully different
  pages, slides, or transcript segments THE SYSTEM SHALL preserve them separately.

---

## Requirement 13 — Frontend Filter Integrity

- THE SYSTEM SHALL send conversation_id, sender_id, source, and content_type as
  filter values from the frontend.
- THE SYSTEM MAY display conversation_title and sender_name for presentation only.
- THE SYSTEM SHALL NOT allow the frontend to construct or transmit an owner_id.

---

## Requirement 14 — Source Card Presentation

- WHEN a source card is rendered THE SYSTEM SHALL display conversation title,
  conversation type, sender name, timestamp, content type, filename (when
  present), and a relevant snippet.
- THE SYSTEM SHALL NOT expose raw internal IDs outside a developer/debug view.

---

## Requirement 15 — Isolation Test Fixtures

- THE SYSTEM SHALL provide fixtures for at least two owners, each with a private
  chat and a group chat, including a duplicate display name ("Anu") referring to
  two distinct people with distinct sender_id/conversation_id values.
- THE SYSTEM SHALL provide at least one file-based (PDF or document) fixture
  carrying full Telegram metadata.
- Each fixture SHALL contain a distinct, checkable fact.

---

## Requirement 16 — End-to-End Isolation Test Coverage

- THE SYSTEM SHALL include end-to-end tests against the real test vector store
  covering all 12 isolation scenarios.
- WHEN any of the above tests is run THE SYSTEM SHALL fail the build if
  isolation is violated in any direction.

---

## Requirement 17 — Backwards Compatibility

- THE SYSTEM SHALL keep the existing upload workflow compiling and functioning.
- THE SYSTEM SHALL keep the existing query schema compatible.
- THE SYSTEM SHALL keep existing retrieved-document fields populated as before.
- THE SYSTEM SHALL keep the existing frontend build passing.
- THE SYSTEM SHALL introduce no new backend test failures beyond the 2 known
  pre-existing ones.
- THE SYSTEM SHALL NOT achieve "no new failures" by broadening test exclusions
  or deleting assertions.

---

## Requirement 18 — Structured Error Handling

- THE SYSTEM SHALL raise typed errors for: unauthorized owner scope, unknown
  conversation, conversation not owned by requesting user, invalid sender,
  unsupported filter combination, malformed timestamp, vector-store filter
  construction failure, missing mandatory metadata, and metadata serialization
  failure.
- THE SYSTEM SHALL NOT expose raw ChromaDB queries, database paths, Telegram
  session details, or internal exception traces in production API responses.

---

## Requirement 19 — Structured Logging Without Sensitive Data

- THE SYSTEM SHALL log: Telegram event normalized, KnowledgeObject converted to
  vector metadata, chunk inserted, query scope built, vector filter built,
  retrieval completed, source response assembled — using IDs and counts.
- THE SYSTEM SHALL NOT log full private message content, OTPs, 2FA passwords,
  Telegram session material, phone numbers, or raw authorization objects.

---

## Requirement 20 — Documentation

- THE SYSTEM SHALL update or create docs/telegram-rag-flow.md,
  docs/telegram-data-model.md, docs/telegram-security.md,
  docs/telegram-filtering.md, and docs/telegram-source-citations.md.
- Documentation SHALL cover the canonical vector metadata contract, stable
  vector ID format, owner-isolation enforcement, filtering, duplicate-name
  handling, source-response structure, ChromaDB filter limitations, test
  coverage, and why live TDLib remains deferred.
- Documentation SHALL include Mermaid diagrams for the data flow.
