# Nexora

> Turn your WhatsApp conversations into a searchable, queryable personal knowledge base — powered by semantic AI.

---

## Problem Statement

Every day, people exchange thousands of messages on WhatsApp — sharing ideas, decisions, links, plans, and memories. Over time, that knowledge becomes buried and impossible to retrieve. Searching for a specific conversation, a shared link, or a past decision means scrolling endlessly through chat history with no semantic understanding.

There is no tool that takes your personal chat data and makes it genuinely **queryable** — not just keyword-searchable, but semantically searchable using the same natural language you used when you wrote the messages.

---

## Solution Overview

Nexora is a production-grade AI Personal Knowledge Engine that ingests WhatsApp chat exports, processes them through a multi-phase semantic pipeline, and ultimately answers natural language questions using Retrieval-Augmented Generation (RAG).

The system is designed for:
- **Privacy-first** — runs entirely locally, no data leaves your machine
- **Multilingual** — handles Arabic, Chinese, Hindi, English, emoji, and mixed-script chats
- **Scale** — engineered for 100,000+ messages with batched, cached, token-accurate processing
- **Extensibility** — clean architecture with clearly separated phases, each independently testable

---

## Completed Phases

### Phase 1 — WhatsApp Ingestion and Parsing

Accepts a WhatsApp export as a `.zip` file or extracted folder, validates it, extracts the chat, parses every message, detects attachments, and produces a fully structured `Chat` object.

**What it does:**
- Detects input type (ZIP or folder)
- Validates and extracts ZIP archives
- Validates dataset structure (chat file + media)
- Parses 12-hour and 24-hour timestamp formats
- Handles multi-line messages and system messages
- Detects attachment references (images, audio, video, documents, stickers)
- Extracts metadata (participants, date range, message count, attachment count)

**Output:** `Chat` object containing `List[Message]`, `List[Attachment]`, `ChatMetadata`

---

### Phase 2 — Document Preparation and Token-Aware Chunking

Converts the raw `Chat` object into clean, normalised, semantically coherent `Document` objects ready for embedding. Uses the BGE-M3 tokenizer (not the full model) for exact token counting.

**What it does:**
- Removes invisible Unicode (zero-width spaces, BOM, direction marks)
- Normalises line endings, whitespace, and typographic punctuation
- NFC-normalises Unicode and title-cases sender names
- Groups messages into overlapping chunks using exact token counts (never estimates)
- Splits oversized single messages at sentence boundaries only
- Enriches each document with metadata (participants, attachments, duration, media flags)

**Chunking strategy:** Message-based (450 tokens max, 50-token overlap). Never splits in the middle of a message unless that single message exceeds the limit.

**Output:** `List[Document]` — immutable, metadata-rich, embedding-ready chunks

---

### Phase 3 — Embedding Generation with BGE-M3

Transforms every `Document` into a dense 1024-dimensional vector using `BAAI/bge-m3` via SentenceTransformers. All embeddings are L2-normalised for cosine similarity compatibility.

**What it does:**
- Lazy-loads the embedding model on first use (no startup cost on import)
- Singleton model instance — loaded once, reused across the entire pipeline
- SHA-256 keyed in-memory cache — identical texts are never embedded twice
- Per-batch cache re-check and within-batch deduplication
- Batch inference (default batch size: 32) — 32× faster than document-by-document
- Validates every embedding (no NaN, no Inf, non-zero norm)
- Preserves all Phase 2 metadata through to the output
- Handles empty-text documents gracefully (zero-vector sentinel)

**Output:** `List[EmbeddedDocument]` — document text + L2-normalised 1024-dim vector + full metadata

---

## Architecture Flow

```
WhatsApp Export (.zip or folder)
           │
           ▼
┌─────────────────────────┐
│   Phase 1 Pipeline      │
│                         │
│  Input Detection        │
│  ZIP Validation         │
│  ZIP Extraction         │
│  Dataset Validation     │
│  Chat Parsing           │
│  Attachment Detection   │
│  Metadata Extraction    │
└──────────┬──────────────┘
           │  Chat object
           │  (participants, messages, metadata)
           ▼
┌─────────────────────────┐
│   Phase 2 Pipeline      │
│                         │
│  Text Cleaning          │
│  Text Normalisation     │
│  Token Counting (BGE)   │
│  Message Chunking       │
│  Document Building      │
│  Metadata Enrichment    │
└──────────┬──────────────┘
           │  List[Document]
           │  (text, metadata, participants, timestamps)
           ▼
┌─────────────────────────┐
│   Phase 3 Pipeline      │
│                         │
│  Embedding Cache        │
│  BGE-M3 (batch encode)  │
│  L2 Normalisation       │
│  Validation             │
│  EmbeddedDocument build │
└──────────┬──────────────┘
           │  List[EmbeddedDocument]
           │  (text + 1024-dim vector + metadata)
           ▼
     [ Phase 4 → Vector DB ]         ← coming next
     [ Phase 5 → Retrieval  ]
     [ Phase 6 → RAG Answer  ]
     [ Phase 7 → API / UI    ]
```

---

## Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.13 |
| Embedding Model | BAAI/bge-m3 (1024-dim, multilingual) |
| Embedding Framework | SentenceTransformers 5.3.0 |
| Tokenizer | HuggingFace Transformers (AutoTokenizer) |
| Tensor Backend | PyTorch 2.11.0 |
| Numerical Computing | NumPy 2.3.2 |
| Testing | pytest 9.1.1 |
| Data Models | Python dataclasses (frozen) |
| Hashing | SHA-256 (hashlib) |
| Type Safety | Python type hints throughout |

---

## Features Completed

- [x] WhatsApp ZIP and folder ingestion
- [x] 12-hour and 24-hour timestamp parsing
- [x] Multi-line message reconstruction
- [x] System message detection
- [x] Attachment reference detection (image, audio, video, document, sticker)
- [x] Participant extraction and metadata computation
- [x] Invisible Unicode removal (zero-width spaces, BOM, direction marks)
- [x] Typographic punctuation normalisation (curly quotes, em-dash, ellipsis)
- [x] Unicode NFC normalisation
- [x] Exact token counting via BGE-M3 tokenizer (no estimation)
- [x] Message-based overlapping chunking (450 tokens / 50 overlap)
- [x] Sentence-boundary splitting for oversized messages
- [x] Frozen, immutable Document and EmbeddedDocument models
- [x] Lazy-loading singleton embedding model
- [x] SHA-256 embedding cache with hit/miss statistics
- [x] Within-batch deduplication (identical texts embedded once per batch)
- [x] Cross-batch cache reuse (texts cached by batch N skip model in batch N+1)
- [x] L2-normalised embeddings (unit-norm, cosine-similarity ready)
- [x] Embedding validation (NaN, Inf, zero-norm detection)
- [x] Full metadata propagation from Phase 1 → Phase 2 → Phase 3
- [x] 203 tests across all three phases

---

## Project Structure

```
nexora/
├── main.py                          # Phase 1 CLI entry point
├── requirements.txt
├── .env.example
│
├── models/                          # Immutable data models
│   ├── chat.py                      # Chat object (Phase 1 output)
│   ├── message.py                   # Individual message
│   ├── attachment.py                # Attachment reference
│   ├── metadata.py                  # Chat-level metadata
│   ├── document.py                  # Semantic chunk (Phase 2 output)
│   └── embedded_document.py         # Vectorised chunk (Phase 3 output)
│
├── pipeline/
│   └── phase1_pipeline.py           # Phase 1 orchestrator
│
├── app/
│   ├── dataset_validator.py
│   ├── extractor.py
│   ├── input_detector.py
│   ├── zip_validator.py
│   ├── documents/                   # Phase 2 sub-package
│   │   ├── cleaner.py               # Unicode / whitespace cleaning
│   │   ├── normalizer.py            # NFC, sender names, punctuation
│   │   ├── tokenizer_service.py     # BGE-M3 tokenizer singleton + cache
│   │   ├── chunker.py               # Message-based overlap chunker
│   │   ├── document_builder.py      # Chunk → Document conversion
│   │   ├── metadata_enricher.py     # Attachment flags, duration, stats
│   │   └── phase2_pipeline.py       # Phase 2 orchestrator
│   └── vectorization/               # Phase 3 sub-package
│       ├── embedding_model.py       # BGE-M3 lazy singleton wrapper
│       ├── embedding_cache.py       # SHA-256 in-memory cache
│       ├── embedding_generator.py   # Document → EmbeddedDocument
│       ├── embedding_batcher.py     # Batched pipeline with deduplication
│       └── embedding_pipeline.py    # Phase 3 orchestrator
│
├── parser/
│   ├── chat_parser.py               # WhatsApp message parser
│   ├── attachment_detector.py       # Media file resolver
│   └── metadata_parser.py          # Chat metadata extractor
│
├── exceptions/
│   └── exceptions.py               # All custom exception types
│
├── utils/
│   ├── datetime_utils.py
│   ├── file_utils.py
│   └── regex_patterns.py
│
├── tests/
│   ├── test_pipeline.py             # Phase 1 — 16 tests
│   ├── test_phase2.py               # Phase 2 — 98 tests
│   └── test_phase3.py               # Phase 3 — 89 tests
│
├── data/
│   ├── raw/                         # Place WhatsApp exports here
│   ├── extracted/                   # ZIP extraction target
│   ├── processed/
│   ├── vectors/                     # Future: vector index files
│   └── logs/
│
└── vectordb/                        # Future: Phase 4 implementation
```

---

## Installation

**Prerequisites:** Python 3.11 or higher

```bash
# 1. Clone the repository
git clone https://github.com/your-username/nexora.git
cd nexora

# 2. Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment template
copy .env.example .env      # Windows
cp .env.example .env        # macOS / Linux
```

The BGE-M3 model (~570 MB) is downloaded automatically from HuggingFace on first use. An internet connection is required for the initial download only; subsequent runs use the local cache.

---

## How to Run

### Phase 1 — Ingest a WhatsApp export

```bash
# From a ZIP file
python main.py path/to/WhatsApp_Export.zip

# From an already-extracted folder
python main.py path/to/whatsapp_chat_folder

# With custom extraction directory and verbose logging
python main.py export.zip --extract-root data/extracted --log-level DEBUG
```

### Phase 1 → Phase 2 → Phase 3 (end-to-end)

```python
from pipeline.phase1_pipeline import Phase1Pipeline
from app.documents.phase2_pipeline import Phase2Pipeline
from app.vectorization.embedding_pipeline import EmbeddingPipeline

# Phase 1: parse the export
chat = Phase1Pipeline("path/to/export.zip").run()

# Phase 2: chunk into documents
documents = Phase2Pipeline(chat).run()

# Phase 3: generate embeddings
embedded = EmbeddingPipeline(documents).run()

print(f"Produced {len(embedded)} embedded documents")
print(f"Embedding dimension: {embedded[0].embedding_dim}")
```

---

## Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run by phase
python -m pytest tests/test_pipeline.py -v    # Phase 1 (16 tests)
python -m pytest tests/test_phase2.py -v      # Phase 2 (98 tests)
python -m pytest tests/test_phase3.py -v      # Phase 3 (89 tests)

# Run with coverage summary
python -m pytest tests/ --tb=short -q
```

> **Note:** Phase 3 tests use a mock embedding model by design. No real model weights are downloaded during testing. The full test suite completes in under 30 seconds.

---

## Test Status

| Phase | Test File | Tests | Status |
|---|---|---|---|
| Phase 1 — Ingestion | `test_pipeline.py` | 16 | ✅ Passing |
| Phase 2 — Documents | `test_phase2.py` | 98 | ✅ Passing |
| Phase 3 — Embeddings | `test_phase3.py` | 89 | ✅ Passing |
| **Total** | | **203** | **✅ All passing** |

---

## Roadmap

| Phase | Description | Status |
|---|---|---|
| Phase 1 | WhatsApp ingestion and parsing | ✅ Complete |
| Phase 2 | Document preparation and token-aware chunking | ✅ Complete |
| Phase 3 | Embedding generation with BGE-M3 | ✅ Complete |
| Phase 4 | Vector database — index and persist `EmbeddedDocument` objects (FAISS / Qdrant / Chroma) | 🔜 Next |
| Phase 5 | Semantic retrieval — top-k similarity search with metadata filtering | ⬜ Planned |
| Phase 6 | RAG answer generation — retrieve relevant chunks, generate answers via LLM | ⬜ Planned |
| Phase 7 | API and UI — REST API (FastAPI) and web interface for querying the knowledge base | ⬜ Planned |
| Phase 8 | Multimodal expansion — process images, audio, and video attachments alongside text | ⬜ Planned |

---

## Author

Built with a focus on clean architecture, production-grade engineering, and long-term maintainability.

- **Project:** Nexora — AI Personal Knowledge Engine
- **Architecture:** Clean Architecture, SOLID principles, dependency injection throughout
- **Philosophy:** Every phase is independently testable, replaceable, and documented

---

*Nexora is a personal knowledge project. All processing runs locally. No data is sent to external servers.*
