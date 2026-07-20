<div align="center">

# Nexora

### Telegram AI Knowledge Retrieval Platform

*Connect your Telegram account, index selected conversations, and query your own history with AI-powered answers.*

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react)](https://react.dev/)
[![ChromaDB](https://img.shields.io/badge/VectorDB-ChromaDB-red?style=flat-square)](https://www.trychroma.com/)
[![BGE-M3](https://img.shields.io/badge/Embeddings-BAAI%2Fbge--m3-yellow?style=flat-square)](https://huggingface.co/BAAI/bge-m3)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)

</div>

---

## What is Nexora?

Nexora is a **private Telegram AI Knowledge Retrieval Platform** powered by Retrieval-Augmented Generation (RAG).

It connects to your Telegram account (via the Telegram Client API / TDLib), indexes only the conversations you select, and lets you search them with natural language questions — answered exclusively from your own messages, with full source citations.

**Telegram is the sole supported data source.** Everything runs locally. No data leaves your machine.

---

## Architecture

```
Telegram Client API (TDLib)
        │
        ▼
Telegram Authentication / Session
        │
        ▼
Chat Discovery and Selection
        │
        ▼
Historical Sync + Live Updates
        │
        ▼
Telegram Message / Media Processing
        │
        ▼
Knowledge Chunk Generation
        │
        ▼
Embedding Generation (BAAI/bge-m3)
        │
        ▼
ChromaDB Vector Store
        │
        ▼
Metadata-Filtered Semantic Retrieval
        │
        ▼
RAG Generation (OpenAI / Ollama)
        │
        ▼
Nexora AI — Cited Answers
```

---

## Key Features

**Telegram Integration**
- Connect via Telegram Client API (TDLib, mock client in current stage)
- Per-chat indexing consent — only future messages, only selected chats
- Private chat and group-sender filtered retrieval
- Edit synchronization (Strategy C: upsert then delete stale)
- Delete synchronization with tombstone replay protection
- DB-backed ownership enforcement

**RAG Pipeline**
- BAAI/bge-m3 multilingual embeddings (1024-dim)
- ChromaDB persistent vector store
- Semantic retrieval with metadata filtering
- Owner isolation enforced server-side
- Timestamp post-filtering (timezone-aware)
- Query-focused snippet extraction

**Security**
- Owner-scoped retrieval — no cross-user data leakage
- Phone numbers and session references encrypted at rest (planned)
- OTPs and 2FA passwords never persisted
- Deleted content removed from retrieval index
- Path-traversal protection on media files

---

## Current Stage: Mock Telegram Client

Live TDLib is not yet integrated. All Telegram operations use `MockTelegramClient`, which replays fixture events from `tests/fixtures/telegram/`. The complete RAG pipeline — normalizer, ingestion policy, deduplication, embedding, storage, retrieval, and RAG — works end-to-end with mock data.

Switching to live TDLib requires only a config change (`NEXORA_TELEGRAM_CLIENT=tdlib`).

---

## Quick Start

```bash
# Backend
pip install -r requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend
cd frontend
npm install
npm run dev
```

---

## Testing

```bash
# Backend
python -m pytest --ignore=tests/test_phase2.py --ignore=tests/test_phase3.py

# Frontend
cd frontend
npm run typecheck
npm run build
```

---

## CI/CD & Deployment

Nexora uses **GitHub Actions** for automated validation, security, and release orchestration.

### Workflows
- **Quality Gates (`ci.yml`)**: Runs on every Push to `main` and Pull Request. Automatically tests both the Python Backend (`pytest`) and the React Frontend (`vitest` + `tsc`), ensuring no broken code reaches the `main` branch.
- **Docker Validation & Registry (`docker.yml`)**: Builds the Docker images to verify production readiness. Pushes images to `ghcr.io` on tags and merges to `main`.
- **Security Scanning (`security.yml`)**: Runs Aqua Security **Trivy** on PRs and a weekly schedule to detect dependency vulnerabilities and exposed secrets.
- **Release Orchestration (`release.yml`)**: Pushing a tag (e.g., `v1.0.0`) automatically bundles the frontend and backend, attaching them as artifacts to an automatically drafted GitHub Release.

### Deployment with Docker Compose
Nexora provides production-ready infrastructure using Docker Compose, orchestrating the Frontend, Backend, Reverse Proxy, PostgreSQL, and ChromaDB.

1. Copy `.env.example` to `.env` and fill in necessary configuration.
2. Start in standard/development mode:
   ```bash
   docker compose up -d --build
   ```
3. Start in production mode (enforces resource limits and log rotation):
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```

---

## Deferred Work

- Phone number encryption
- Telegram session reference encryption
- Live TDLib integration
- Sender membership DB validation
- Full edit embedding regeneration (multi-chunk)
- Multi-chunk PDF/PPTX/voice edit handling
