# Telegram Source Citations

## Overview (Requirement 12)

Every RAG query response that includes Telegram-sourced chunks now returns
a `sources` array of `TelegramSourceResponse` objects alongside the existing
`retrieved_documents` and `citations` arrays.

`sources` is an additive field — existing clients that ignore it are
unaffected.

## TelegramSourceResponse schema

```json
{
  "document_id": "telegram:acc_001:conv_001:msg_001:text:0",
  "source": "telegram",
  "conversation_id": "tg_chat_anu_001",
  "conversation_title": "Anu",
  "conversation_type": "private",
  "sender_id": "tg_user_anu_001",
  "sender_name": "Anu",
  "message_id": "tg_message_1001",
  "timestamp": "2026-07-13T18:30:00+05:30",
  "content_type": "text",
  "filename": "",
  "chunk_index": 0,
  "snippet": "The project report must be submitted before Monday.",
  "score": 0.8732
}
```

## Security constraints

- `owner_id` is **never** included in source responses
- `file_path` (local filesystem path) is **never** included
- `phone_number` is **never** included
- Session tokens and auth details are **never** included
- `sender_id` is included for programmatic use; `sender_name` is for display

## Deduplication logic

When multiple chunks originate from the same message:

| Condition | Behavior |
|---|---|
| Same `(source_message_id, content_type)`, no differentiating fields | Keep highest-scoring chunk only |
| Different `page_number` (PDF pages) | Preserve both separately |
| Different `slide_number` (PPTX slides) | Preserve both separately |
| Different `transcript_segment` (voice/video) | Preserve both separately |

## Source card display (Requirement 14)

`TelegramSourceCard` renders:
- Conversation title + type icon (private / group / channel)
- Sender name (display-only; never used as filter)
- Timestamp (human-readable)
- Content type + filename (when applicable)
- Relevant snippet (up to 200 chars)

Raw IDs (`document_id`, `message_id`, `conversation_id`, `sender_id`) are
hidden behind a collapsible `<details>` element labeled "Debug IDs".

## Frontend filter integrity (Requirement 13)

The frontend sends `conversation_id`, `sender_id`, `source`, and
`content_type` as stable identifiers when constructing queries.
`conversation_title` and `sender_name` are display-only and are **never**
sent as filter values. `owner_id` is **never** transmitted by the frontend.
