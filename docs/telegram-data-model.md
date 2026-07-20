# Nexora Telegram Data Model

## KnowledgeObject (Central Domain Model)

`models/knowledge_object.py` — [ADDITIVE]

The source-independent unit flowing through the entire pipeline.
No WhatsApp-specific concepts. All sources produce KnowledgeObjects.

### Key Fields

| Field | Type | Purpose |
|---|---|---|
| `owner_id` | str | Security boundary. Every retrieval MUST filter on this. |
| `source` | str | Platform identifier: "telegram", "whatsapp", etc. |
| `source_account_id` | str | Which account on the source platform |
| `conversation_id` | str | Stable chat/group identifier |
| `source_message_id` | str | Platform's own message ID — deduplication key |
| `sender_id` | str\|None | Stable sender identifier (retrieval key, NOT sender_name) |
| `sender_name` | str\|None | Display name only — never use for filtering |
| `content_type` | str | Routes to content processor |
| `timestamp` | datetime | Always timezone-aware |
| `is_edited` | bool | Triggers re-indexing |
| `is_deleted` | bool | Triggers removal from index |

### Stable Vector Document ID

```
{source}:{account_id}:{chat_id}:{message_id}:{content_part}:{chunk_index}

Example: telegram:tg_account_001:tg_chat_anu_001:tg_message_1001:text:0
         telegram:tg_account_001:tg_chat_anu_001:tg_message_1001:pdf:2
```

Deterministic — same message always maps to the same vector ID, preventing duplicates.

## Operational Database Models

`app/integrations/telegram/models/telegram_models.py` — [ADDITIVE]

### TelegramAccount

Represents one connected Telegram user account.

- `phone_number_encrypted` — never plaintext
- `session_reference` — opaque, never contains OTP or 2FA password
- `authorization_status` — one of: disconnected / waiting_phone / waiting_code / waiting_password / ready / closed / error

Unique constraint: `(owner_id, telegram_user_id)`

### TelegramChat

One Telegram chat with per-chat indexing configuration.

- `indexing_enabled` — must be True for any message to be processed
- `indexing_enabled_at` — messages before this timestamp are NEVER indexed
- `last_processed_message_id` — stable cursor for resuming after restart

Unique constraint: `(owner_id, telegram_account_id, telegram_chat_id)`

### TelegramMessage

Source-of-truth record for a message as received from Telegram.

- Tracks `is_edited`, `is_deleted`, `edit_count`
- `processing_status` lifecycle: PENDING → PROCESSING → COMPLETED / FAILED

Unique constraint: `(telegram_account_id, telegram_chat_id, telegram_message_id)`

### TelegramAttachment

File attachment with download and processing lifecycle tracking.

- `checksum` (SHA-256) generated after download
- `local_path` is relative to media root — never absolute paths

### TelegramIndexingPreference

Fine-grained per-chat indexing preferences (text, images, voice, documents).

### TelegramProcessingState

Account/chat-level processing state with pause/resume support.

## Vector Metadata Schema

Every embedded chunk carries:

```json
{
  "owner_id": "user_123",
  "source": "telegram",
  "source_account_id": "tg_account_001",
  "conversation_id": "tg_chat_anu_001",
  "sender_id": "tg_user_anu_001",
  "sender_name": "Anu",
  "source_message_id": "tg_message_1001",
  "content_type": "text",
  "timestamp": "2026-07-13T18:30:00+05:30",
  "filename": null,
  "chunk_index": 0
}
```

`owner_id` + `source` form the mandatory primary security filter.
`conversation_id` and `sender_id` are optional secondary filters.
