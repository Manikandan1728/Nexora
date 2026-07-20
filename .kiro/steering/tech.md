# Nexora — Tech Stack

Backend: FastAPI, Pydantic, ChromaDB (confirm installed version before
assuming `where` filter syntax), existing embedding pipeline (do not replace).

Frontend: React, TypeScript.

Testing: existing backend suite (baseline: 523 passed / 2 known pre-existing
failures), 87 Telegram-specific tests, frontend typecheck + production build.

Constraint: MockTelegramClient only — no live TDLib in this milestone.
