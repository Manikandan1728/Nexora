# Telegram Part 2C Audit - Telethon Authentication Integration

## Current Authentication State Machine
The current backend state machine is purely mocked inside `api/routes/telegram.py` and transitions trivially:
*   `disconnected` -> `waiting_phone` (on `/connect`)
*   `waiting_phone` -> `waiting_code` (on `/auth/phone` via `TelegramPhoneAuthorizationService`)
*   `waiting_code` -> `ready` (on `/auth/code`)
*   `waiting_password` -> `ready` (on `/auth/password`)

The real state machine will use: `DISCONNECTED`, `PHONE_REQUIRED`, `CODE_SENT`, `PASSWORD_REQUIRED`, `AUTHENTICATED`, `SESSION_INVALID`, `ERROR`.

## Current Mock Client Contract
No unified client gateway interface exists. There is a `MockTelegramClient` in `app/integrations/telegram/client/mock_telegram_client.py` and some TDLib stubs, but routes are hardcoded to `MockTelegramClient` or inline logic.

## Current API Request and Response Schemas
- `ConnectRequest`, `ConnectResponse`
- `PhoneRequest`, `CodeRequest`, `PasswordRequest`
- `AuthResponse`, `TelegramStatusResponse`, `TelegramPhoneSubmissionResult`
Schemas use safe DTOs (e.g., `SecretStr` for inputs). No sensitive values are returned. `phone_number_masked` is already implemented.

## Current Session Persistence Mechanism
- `TelegramSessionSecretService` exists with contexts for TDLib (`tdlib_database_key`, etc.) but lacks `telegram_mtproto_session` context and Telethon `StringSession` support.
- `TelegramAccountORM` contains `session_reference_encrypted` and other TDLib fields. No plaintext is persisted.

## Database Fields
`TelegramAccountORM` fields:
- `id`, `owner_id`, `telegram_user_id` (currently hardcoded as `mock_user_001` in mock)
- `phone_number_encrypted`, `authorization_status`, `session_status`
- `session_reference_encrypted`, `tdlib_database_key_encrypted`, `tdlib_files_database_key_encrypted`, `session_locator_encrypted`
- We will need to store `session_encrypted` (or reuse one of the fields) for the Telethon `StringSession`.
- We need an explicit migration strategy for these fields if adding a new one.

## Temporary Authentication State
Currently, no temporary authentication state (like `phone_code_hash`) is persisted. We need an in-memory/cache transaction store to track `authentication_attempt_id` mapped to `phone_code_hash` and `phone_number_encrypted` (or raw briefly in-memory to initialize Telethon).

## Existing Security Boundaries
- `TelegramPhoneSecretService` prevents plaintext persistence.
- `TelegramSessionSecretService` exists but needs adaptation to `StringSession`.
- API endpoints do not log raw phone numbers, codes, or passwords.
- Pydantic `SecretStr` is heavily utilized.

## Files Requiring Modification
- `api/routes/telegram.py` (wire the interface and real logic instead of mock)
- `app/integrations/telegram/security/session_secret_service.py` (add StringSession context)
- `api/services/telegram_auth_service.py` (real authentication transaction management)
- `app/integrations/telegram/db/orm_models.py` (potential new fields/migrations)
- `frontend/src/features/telegram/TelegramConnectionPage.tsx` (real modes, loading states, 2FA password)
- `frontend/src/api/telegram.service.ts` (handle `auth_state` and real error mapping)
- `api/config.py` (add `TELEGRAM_MODE`, `TELEGRAM_API_ID`, etc.)
- `.env.example`

## Files that must remain unchanged
- `app/security/secrets/base.py` (SecretStore itself)
- `app/integrations/telegram/security/phone_secret_service.py` (already working correctly)

## Compatibility Risks
- Hardcoded `mock_user_001` in routes must be dynamically fetched or resolved.
- Frontend might assume immediate mock transitions without dealing with network latencies.
