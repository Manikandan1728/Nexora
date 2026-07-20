# Nexora Telegram Security

## Credential Handling

| Credential | Policy |
|---|---|
| Phone number | Encrypted at rest (`phone_number_encrypted`). Never logged. Never returned in API responses. |
| OTP verification code | Never persisted. Discarded immediately after the auth call. |
| Two-step verification password | Never persisted. Discarded immediately. |
| TDLib session | Stored as opaque reference only. Session secrets never appear in application state, logs, or API responses. |

## Owner Isolation

Every KnowledgeObject, vector chunk, and retrieval query carries `owner_id`.

- All vector metadata includes `owner_id`.
- All retrieval queries **must** include `owner_id` as a mandatory filter.
- Cross-owner data leakage is prevented at the ChromaDB query level.

## Per-Chat Consent

- Indexing is opt-in per chat (`indexing_enabled = false` by default).
- Only messages received **after** the user enables indexing are processed.
- The user can disable indexing and delete all indexed data per chat at any time.

## Media Safety

- `local_path` in `TelegramAttachment` is always relative to the media root — never an absolute path.
- Filenames are sanitised before storage (no path separators, no null bytes).
- MIME types are validated against an allowlist before processing.
- File size limits are enforced before download.
- Attachment checksums (SHA-256) are generated after download for integrity verification.

## Logging Policy

- Phone numbers, OTP codes, and 2FA passwords are never logged at any level.
- Raw message content is not logged at INFO or above in production.
- Sender IDs are logged (stable, non-sensitive identifiers). Sender names are not logged.
- Session file paths are logged; session secrets are not.

## Delete Controls

- Per-chat delete: `DELETE /integrations/telegram/chats/{chat_id}/data`
  Removes all vector entries for that chat.
- Telegram delete sync: when Telegram reports a message deletion, indexed chunks are removed.
- Deleted content is no longer retrievable through any RAG query.

## Input Validation

- All API request bodies are validated with Pydantic models.
- `owner_id` and `sender_id` are always strings — no integer overflow risk.
- Metadata filter fields are validated against a strict allowlist in `MetadataFilter`.
- Mock event ingestion validates the event structure before normalization.
