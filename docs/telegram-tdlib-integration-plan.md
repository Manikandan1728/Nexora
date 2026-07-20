# TDLib Integration Plan

## Current State

`MockTelegramClient` is the active client. It replays fixture events from
`tests/fixtures/telegram/` and simulates authorization states. No real
Telegram network calls are made.

The stub `TDLibTelegramClient` (`app/integrations/telegram/client/tdlib_client.py`)
raises `NotImplementedError` on all methods. It is **not** wired into the
runtime path.

`NEXORA_TELEGRAM_CLIENT=mock` is the default and only working value.

## Activation Condition

`TDLibTelegramClient` may be wired into the active path only when:

1. A native TDLib binary is present and loadable (via `python-telegram` or `pytdbot`).
2. All `TDLibTelegramClient` methods are implemented and tested.
3. Authorization flow (phone → OTP → optional 2FA) passes integration tests.
4. The mock test suite continues to pass in parallel.
5. `NEXORA_TELEGRAM_CLIENT=tdlib` is set explicitly — never automatic.

## Implementation Steps (Phase 15)

```
1. Install python-telegram or pytdbot (TDLib Python bindings)
2. Implement TDLibTelegramClient.connect() — initialize TDLib client
3. Implement get_authorization_state() — poll TDLib auth state
4. Implement submit_phone_number() — call setAuthenticationPhoneNumber
5. Implement submit_code() — call checkAuthenticationCode
6. Implement submit_password() — call checkAuthenticationPassword
7. Implement list_chats() — call getChats + getChat
8. Implement updates() — yield from TDLib update stream
9. Implement download_file() — call downloadFile
10. Wire into api/routes/telegram.py via NEXORA_TELEGRAM_CLIENT env var
11. Run full test suite with mock (must still pass)
12. Run integration tests with live TDLib (separate test suite)
```

## Interface Contract

`TDLibTelegramClient` must implement `TelegramClient` protocol exactly:

```python
from app.integrations.telegram.client.base_telegram_client import TelegramClient
assert isinstance(TDLibTelegramClient(), TelegramClient)  # must pass
```

## Why Not Bot API

| Capability | Bot API | Client API (TDLib) |
|---|---|---|
| Read private conversations | ❌ No | ✅ Yes |
| Read group history | Only if bot is member | ✅ Yes |
| Observe future messages passively | ❌ No | ✅ Yes |
| Work without other party adding bot | ❌ No | ✅ Yes |
| Access all user's chats | ❌ No | ✅ Yes |

A personal knowledge assistant that indexes the user's own conversations
requires the Client API. The Bot API is sufficient only for bots that
interact with users who explicitly message the bot.

## Session Security

- TDLib session files are stored outside the application's working directory.
- `session_reference` in `TelegramAccount` is an opaque path reference.
- Session files must be excluded from version control (`.gitignore`).
- Session files must be encrypted at rest in production deployments.
