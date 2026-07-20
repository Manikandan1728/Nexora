# Nexora — Telegram Phone-Number Encryption (Part 2B) — Standing Rules

- Reuse the existing SecretStore. Never add a second encryption implementation or call AES-GCM directly outside the secret-store package.
- Encryption context is always exactly: telegram_phone_number
- Never persist, log, or return plaintext phone numbers. Never return ciphertext through any API or frontend surface — only phone_number_masked.
- Never add a plaintext phone_number persistence column.
- Decryption may only happen inside TelegramPhoneSecretService or another explicitly-authorized trusted service — never in API routes, ORM models, response serializers, or the frontend.
- Do not double-encrypt values already in nexora:v1: format.
- Preserve all existing Telegram/RAG/edit/delete/reconciliation tests. The same 2 known pre-existing failures may remain; no new failures are allowed.
- Full rule text: see CRITICAL RULES in this document.
