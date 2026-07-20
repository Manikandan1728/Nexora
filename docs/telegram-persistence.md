# Nexora Telegram Persistence

## Overview

Nexora uses SQLite (via SQLAlchemy 2.0) for all Telegram operational data.
The database file lives at `data/storage/nexora_telegram.db` (configurable
via `NEXORA_TELEGRAM_DB_PATH`).

## Tables

| Table | Purpose |
|---|---|
| `tg_accounts` | Connected Telegram user accounts |
| `tg_chats` | Telegram chats with per-chat indexing configuration |
| `tg_messages` | Telegram messages with lifecycle state (edited, deleted) |
| `tg_attachments` | File attachments with download/processing state |
| `tg_message_chunks` | Message-to-vector-ID mapping (chunk tracking) |
| `tg_processing_states` | Idempotency and operation state for all sync operations |
| `tg_deletion_tombstones` | Permanent record of deleted messages (prevents replay) |

## Schema Initialization

Schema is created on first startup via `create_all_tables()`.
No Alembic migration runner is used — the project uses SQLAlchemy's
`Base.metadata.create_all()` pattern.

### Down-migration (rollback)

To fully remove the Telegram persistence layer:

```sql
DROP TABLE IF EXISTS tg_deletion_tombstones;
DROP TABLE IF EXISTS tg_processing_states;
DROP TABLE IF EXISTS tg_message_chunks;
DROP TABLE IF EXISTS tg_attachments;
DROP TABLE IF EXISTS tg_messages;
DROP TABLE IF EXISTS tg_chats;
DROP TABLE IF EXISTS tg_accounts;
```

Or: `DELETE data/storage/nexora_telegram.db` to remove the entire database.

## Key Constraints

- `tg_accounts`: UNIQUE `(owner_id, telegram_user_id)`
- `tg_chats`: UNIQUE `(telegram_account_id, telegram_chat_id)`
- `tg_messages`: UNIQUE `(telegram_account_id, telegram_chat_id, telegram_message_id)`
- `tg_message_chunks`: UNIQUE `vector_id`
- `tg_processing_states`: UNIQUE `idempotency_key`
- `tg_deletion_tombstones`: UNIQUE `(source_account_id, conversation_id, source_message_id)`

## Processing State Lifecycle

```
pending → processing → completed
                    ↘ failed
                    ↘ cleanup_pending
```

## TelegramMessageChunk

Maps each Telegram message to its ChromaDB vector IDs.
Critical for deterministic edit replacement and complete deletion.

Fields:
- `vector_id`: ChromaDB document ID (`telegram:{account}:{chat}:{msg}:{part}:{idx}`)
- `is_active`: False when superseded by an edit or deleted
- `message_version`: Increments on each edit
