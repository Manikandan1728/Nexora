# Nexora Telegram Filtering

## Filter Schema (Requirement 5)

Extended `TelegramMetadataFilter` supports all Telegram identity fields
alongside existing legacy fields.

### New Telegram fields

| Field | Type | Description |
|---|---|---|
| `owner_id` | str | Owner identifier (server-overrides client value) |
| `source` | str | Platform: "telegram", "whatsapp", etc. |
| `source_account_id` | str | Telegram account ID |
| `conversation_id` | str | Single conversation/chat ID |
| `conversation_ids` | List[str] | Multiple conversation IDs |
| `sender_id` | str | Stable sender identifier (never display name) |
| `content_type` | str | Single content type |
| `content_types` | List[str] | Multiple content types |
| `source_message_id` | str | Specific message ID |
| `timestamp_from` | str | ISO-8601 lower bound |
| `timestamp_to` | str | ISO-8601 upper bound |

### Preserved legacy fields

`source_chat`, `chunk_index`, `token_count`, `message_count`,
`attachment_count`, `contains_images`, `contains_audio`, `contains_video`,
`contains_documents`, `embedding_model`, `schema_version`.

### Validation rules

- Empty-string identifier fields are rejected (not treated as "no filter")
- `conversation_id` and `conversation_ids` are mutually exclusive
- `content_type` and `content_types` are mutually exclusive
- Unsupported `content_type` values are rejected
- Malformed ISO-8601 timestamps are rejected

## Owner Isolation (Requirement 6)

`QueryScopeBuilder.build(authenticated_owner_id, requested_filters)` enforces:

1. `effective.owner_id = authenticated_owner_id` — **always**, unconditionally
2. Any client-supplied `owner_id` in `requested_filters` is silently overridden
3. Each `conversation_id` / `conversation_ids` entry is verified against the
   authenticated owner via `IChatOwnershipChecker`

The returned `EffectiveMetadataFilter.owner_id` is always the server-side
authenticated identity, never the client-supplied value.

## ChromaWhereBuilder (Requirement 7)

**Location:** `app/retrieval/chroma_where_builder.py`  
**ChromaDB version verified:** 1.5.9  
**Confirmed operators:** `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$and`, `$or`, `$in`

### Filter construction patterns

#### Private-chat query
```python
{"$and": [
    {"owner_id": {"$eq": "owner_001"}},
    {"source": {"$eq": "telegram"}},
    {"conversation_id": {"$eq": "tg_chat_anu_001"}},
]}
```

#### Group + sender query
```python
{"$and": [
    {"owner_id": {"$eq": "owner_001"}},
    {"source": {"$eq": "telegram"}},
    {"conversation_id": {"$eq": "tg_group_project"}},
    {"sender_id": {"$eq": "tg_user_anu_001"}},
]}
```

#### Multi-conversation query
```python
{"$and": [
    {"owner_id": {"$eq": "owner_001"}},
    {"source": {"$eq": "telegram"}},
    {"conversation_id": {"$in": ["tg_chat_anu", "tg_chat_arun"]}},
]}
```

### Timestamp filtering — known limitation

ChromaDB 1.5.9 stores timestamps as ISO-8601 strings. String comparison
is lexicographic, not chronological, and is only reliable for UTC timestamps
with a consistent format. The `ChromaWhereBuilder` applies a string-based
`$gte`/`$lte` prefilter as a best-effort narrowing pass. **The caller
(query_service) MUST apply an application-level post-filter using actual
`datetime` comparisons for correctness.** Both paths are tested.

## API examples

### Private-chat query
```json
POST /query
{
  "question": "What deadline did Anu mention?",
  "collection_name": "nexora_knowledge",
  "filters": {
    "source": "telegram",
    "conversation_id": "tg_chat_anu_001"
  }
}
```

### Group-sender query
```json
{
  "question": "What did Anu say about the assignment?",
  "collection_name": "nexora_knowledge",
  "filters": {
    "source": "telegram",
    "conversation_id": "tg_group_project_001",
    "sender_id": "tg_user_anu_001"
  }
}
```

### Multi-conversation query
```json
{
  "question": "Where was the deadline discussed?",
  "collection_name": "nexora_knowledge",
  "filters": {
    "source": "telegram",
    "conversation_ids": ["tg_chat_anu_001", "tg_chat_arun_001"]
  }
}
```

### Invalid: client spoofing owner_id
The `owner_id` field in `filters` is always overridden by the authenticated
owner from the server context. A client cannot retrieve another user's data
by supplying a different `owner_id` — it will be silently replaced.
