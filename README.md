<div align="center">

# Nexora

### AI-Powered Personal Knowledge Engine

*Transform your WhatsApp conversations into a semantic knowledge base — query your own history in natural language.*

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/Tests-542%20Passing-brightgreen?style=flat-square&logo=pytest)](https://pytest.org/)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)
[![Architecture](https://img.shields.io/badge/Architecture-Clean%20%2B%20SOLID-orange?style=flat-square)](docs/)
[![RAG](https://img.shields.io/badge/RAG-Grounded%20Generation-purple?style=flat-square)](app/generation/)
[![ChromaDB](https://img.shields.io/badge/VectorDB-ChromaDB-red?style=flat-square)](https://www.trychroma.com/)
[![BGE-M3](https://img.shields.io/badge/Embeddings-BAAI%2Fbge--m3-yellow?style=flat-square)](https://huggingface.co/BAAI/bge-m3)
[![Status](https://img.shields.io/badge/Status-Phase%206%20Complete-success?style=flat-square)]()

</div>

---

Nexora is a production-grade, locally-running AI system that ingests exported WhatsApp conversations, builds a persistent semantic vector index, and answers natural language questions using Retrieval-Augmented Generation. Every phase — from ZIP parsing to grounded LLM answers with citations — is independently tested, immutable-by-design, and built with Clean Architecture and SOLID principles throughout.

---

## Table of Contents

- [Introduction](#introduction)
- [Problem Statement](#problem-statement)
- [Solution](#solution)
- [Features](#features)
- [Architecture](#architecture)
- [Pipeline — Phase by Phase](#pipeline--phase-by-phase)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Example Queries](#example-queries)
- [Testing](#testing)
- [Performance](#performance)
- [Design Principles](#design-principles)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)
- [Author](#author)

---

## Introduction

WhatsApp is where decisions get made, files get shared, and plans get written. After months or years of conversations, that information becomes practically inaccessible — buried under thousands of messages with no way to surface it beyond scrolling.

Nexora solves this by treating your chat history as a knowledge base. It parses your WhatsApp export, splits messages into semantically coherent chunks, embeds them using the multilingual BAAI/bge-m3 model, stores the vectors in a persistent ChromaDB collection, and exposes a retrieval-augmented generation interface that answers questions about your own conversations — grounded exclusively in what was actually said, with full citations.

Everything runs locally. No data leaves your machine.

---

## Problem Statement

WhatsApp's built-in search is keyword-only: it finds exact words, not meaning. Searching for *"the PDF Naveen sent about counselling"* fails unless you remember the exact phrasing. Searching for *"project deadline discussion"* returns nothing if the actual messages used different words.

Beyond search, the fundamental problem is **knowledge retrieval at scale**:

- Conversations accumulate hundreds of thousands of messages over years
- Important decisions, links, and files are mixed with casual small talk
- Context is lost — a message from six months ago has no visible connection to a message from today on the same topic
- There is no structure — chat history is a flat, time-ordered list

Nexora imposes structure, semantics, and retrievability on that flat list.

---

## Solution

Nexora implements a six-phase pipeline that progressively transforms raw chat data into queryable knowledge:

1. **Parse** — extract every message, attachment reference, and metadata field from a WhatsApp ZIP export
2. **Chunk** — group messages into semantically coherent, token-bounded document chunks
3. **Embed** — convert each chunk into a 1024-dimensional L2-normalised vector using BAAI/bge-m3
4. **Store** — persist vectors and metadata in ChromaDB with schema validation
5. **Retrieve** — embed the user's query with the same model and find the top-k most similar chunks
6. **Generate** — pass the retrieved context to an LLM (OpenAI or Ollama) with a grounding prompt that forbids hallucination, and return a cited answer

The key insight behind RAG is that the LLM never uses its parametric memory for your personal data — it only reads the retrieved context. Every answer is grounded in documents that actually exist in your knowledge base, and every claim is backed by a citation pointing to the exact chunk.

---

## Features

**Ingestion**
- [x] WhatsApp ZIP and extracted folder ingestion
- [x] Automatic input type detection (ZIP vs folder)
- [x] ZIP integrity validation before extraction
- [x] 12-hour and 24-hour timestamp format parsing
- [x] Multi-line message reconstruction
- [x] System message detection and labelling
- [x] Attachment reference detection — images, audio, video, documents, stickers
- [x] Participant extraction and deduplication
- [x] Chat-level metadata (date range, message count, attachment count)

**Document Processing**
- [x] Invisible Unicode removal (zero-width spaces, BOM, direction marks)
- [x] Unicode NFC normalisation
- [x] Typographic punctuation normalisation (curly quotes, em-dash, ellipsis)
- [x] Line ending normalisation (CRLF, CR, LF)
- [x] Sender name title-casing and deduplication
- [x] Exact token counting via BGE-M3 tokenizer — no estimation
- [x] Message-based overlapping chunking (450 tokens max, 50-token overlap)
- [x] Sentence-boundary splitting for oversized single messages
- [x] Per-chunk metadata enrichment (media flags, duration, avg message length)

**Embeddings**
- [x] BAAI/bge-m3 — 1024-dimensional, multilingual, L2-normalised
- [x] Lazy-loading singleton model — loaded once, reused across pipeline
- [x] SHA-256 keyed in-memory embedding cache
- [x] Within-batch text deduplication — identical texts embedded once
- [x] Cross-batch cache reuse — prior batches' results served from cache
- [x] Batch inference (default 32 docs/call) for throughput efficiency
- [x] Embedding validation — NaN, Inf, and zero-norm detection

**Vector Storage**
- [x] ChromaDB PersistentClient — survives process restarts
- [x] HNSW cosine similarity index
- [x] Schema versioning — model/version mismatch detection on reopen
- [x] Batched insertion with duplicate skipping
- [x] Full metadata stored alongside every vector

**Retrieval**
- [x] Query preprocessing — Unicode normalisation, whitespace collapse
- [x] Query embedding using the same BGE-M3 singleton
- [x] ANN similarity search with configurable top-k
- [x] Score threshold filtering
- [x] Metadata filtering with equality and comparison operators
- [x] Supported filter fields: source_chat, chunk_index, token_count, message_count, attachment_count, contains_images, contains_audio, contains_video, contains_documents, embedding_model, schema_version
- [x] Distance-to-similarity conversion (cosine, L2, inner product)

**Answer Generation (RAG)**
- [x] Context builder — formats retrieved chunks with rank, score, and metadata
- [x] Token budget enforcement — context never exceeds configured limit
- [x] Grounding prompt — LLM instructed to answer only from supplied context
- [x] Hallucination prevention — explicit "do not use outside knowledge" rules
- [x] Fallback response — "I could not find that information in your knowledge base."
- [x] OpenAI provider — `chat.completions.create` with full parameter control
- [x] Ollama provider — local models via standard HTTP API, zero dependencies
- [x] Citation builder — provenance records from retrieval metadata, no LLM fabrication
- [x] Confidence score — mean retrieval similarity across cited documents
- [x] Token usage tracking per generation call

**Engineering**
- [x] Clean Architecture — six independently deployable phases
- [x] SOLID principles throughout
- [x] Dependency injection on every pipeline and provider
- [x] Frozen/immutable dataclass models (Chat, Document, EmbeddedDocument, RetrievedDocument, GroundedAnswer, Citation)
- [x] Custom typed exceptions per domain (22 exception classes)
- [x] Full type hints across all modules
- [x] 542 automated tests — unit, integration, mocked pipeline
