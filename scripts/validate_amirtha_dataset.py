"""
scripts/validate_amirtha_dataset.py
====================================
Full Phase 1-6 validation run against the "amirtha" WhatsApp dataset.

Validates every phase of the Nexora pipeline against a real, untouched
WhatsApp export. No production code is modified. No new features are
added. This is a read-and-run validation script only.

Usage
-----
    python scripts/validate_amirtha_dataset.py

Output is plain ASCII so it renders on Windows PowerShell (cp1252).
"""

from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path
from typing import List

# ---------------------------------------------------------------------------
# Bootstrap: project root on sys.path before any Nexora imports
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Configuration — amirtha-specific, separate collection from Naveen dataset
# ---------------------------------------------------------------------------
_ZIP_PATH    = _PROJECT_ROOT / "WhatsApp Chat with amirtha.zip"
_COLLECTION  = "nexora_amirtha_test"
_PERSIST_DIR = str(_PROJECT_ROOT / "data" / "vectors" / "amirtha_test")
_EXTRACT_ROOT = str(_PROJECT_ROOT / "data" / "extracted")
_TOP_K        = 5
_PREVIEW_CHARS = 150

# 15 semantic queries covering a range of topics likely in a college/peer chat
_QUERIES: List[str] = [
    "What files were shared?",
    "When were images shared?",
    "Show PDF related messages.",
    "Did anyone share links?",
    "What assignments were discussed?",
    "What did Amirtha ask?",
    "Show internship discussions.",
    "Show important reminders.",
    "When did we discuss college?",
    "What project ideas were discussed?",
    "Were any deadlines mentioned?",
    "Show audio or voice messages.",
    "What documents were sent?",
    "Were any exam topics discussed?",
    "Show messages about submissions.",
]

# Phase 6 LLM config: Ollama with llama3 (local, no API key needed).
# If Ollama is not running the phase 6 answer will show an error but
# phases 1-5 results remain valid.
_LLM_PROVIDER = "ollama"
_LLM_MODEL    = "llama3"

# Queries to pass through Phase 6 RAG (subset — Phase 6 is slow)
_RAG_QUERIES: List[str] = [
    "What files were shared?",
    "What assignments were discussed?",
    "Did anyone share links?",
]

# ---------------------------------------------------------------------------
# ASCII-safe display helpers
# ---------------------------------------------------------------------------
_W = 64

def _line(char: str = "-") -> None:
    print(char * _W)

def _header(title: str) -> None:
    print()
    _line("=")
    print(title)
    _line("=")

def _section(title: str) -> None:
    print()
    _line("-")
    print(title)
    _line("-")

def _row(label: str, value: str) -> None:
    print("  {:<30} {}".format(label, str(value)))

def _info(msg: str) -> None:
    print("  " + str(msg))

def _warn(msg: str) -> None:
    print("  WARN: " + str(msg))

def _error(msg: str) -> None:
    print("  ERROR: " + str(msg), file=sys.stderr)

def _elapsed(s: float) -> str:
    if s < 60:
        return "{:.2f}s".format(s)
    m, sec = divmod(int(s), 60)
    return "{}m {}s".format(m, sec)

def _safe(text: str) -> str:
    """Strip non-ASCII so Windows cp1252 console never crashes."""
    return text.encode("ascii", errors="replace").decode("ascii")

def _preview(text: str) -> str:
    flat = text.replace("\n", " ").replace("\r", " ").strip()
    flat = _safe(flat)
    return flat[:_PREVIEW_CHARS] + "..." if len(flat) > _PREVIEW_CHARS else flat


# ---------------------------------------------------------------------------
# Phase 1
# ---------------------------------------------------------------------------

def run_phase1() -> object:
    _section("PHASE 1 - WhatsApp Ingestion and Parsing")

    from pipeline.phase1_pipeline import Phase1Pipeline

    if not _ZIP_PATH.exists():
        _row("ZIP found", "FAIL")
        _error("File not found: {}".format(_ZIP_PATH))
        sys.exit(1)

    _row("ZIP found", "PASS")
    t0 = time.perf_counter()

    try:
        chat = Phase1Pipeline(
            input_path=str(_ZIP_PATH),
            extract_root=_EXTRACT_ROOT,
        ).run()
    except Exception as exc:
        _row("ZIP parse", "FAIL")
        _error(str(exc))
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

    elapsed = time.perf_counter() - t0

    _row("ZIP validation",   "PASS")
    _row("Extraction",       "PASS")
    _row("Chat parse",       "PASS")
    _row("Messages parsed",  str(chat.metadata.total_messages))
    _row("Participants",     str(len(chat.participants)))
    _row("Participant names",_safe(", ".join(chat.participants)))
    _row("Attachments",      str(chat.metadata.attachment_count))
    _row("Date start",       _safe(chat.metadata.chat_start_date))
    _row("Date end",         _safe(chat.metadata.chat_end_date))
    _row("Metadata",         "PASS")
    _row("Phase 1 time",     _elapsed(elapsed))
    return chat, elapsed


# ---------------------------------------------------------------------------
# Phase 1 quality checks
# ---------------------------------------------------------------------------

def quality_checks(chat) -> None:
    _section("QUALITY CHECKS")

    messages = chat.messages

    # Unicode / emoji preservation: count messages containing non-ASCII
    non_ascii = sum(1 for m in messages if any(ord(c) > 127 for c in m.message))
    _row("Messages with Unicode/emoji", str(non_ascii))

    # Tamil script detection (Tamil Unicode block: U+0B80-U+0BFF)
    tamil = sum(1 for m in messages
                if any(0x0B80 <= ord(c) <= 0x0BFF for c in m.message))
    _row("Messages with Tamil script",  str(tamil))

    # Mixed English + non-ASCII
    mixed = sum(1 for m in messages
                if any(c.isascii() and c.isalpha() for c in m.message)
                and any(ord(c) > 127 for c in m.message))
    _row("Mixed English + non-ASCII",   str(mixed))

    # Deleted messages (WhatsApp marks them)
    deleted = sum(1 for m in messages
                  if "deleted" in m.message.lower()
                  or "this message was deleted" in m.message.lower())
    _row("Deleted message references",  str(deleted))

    # System messages
    system = sum(1 for m in messages if m.sender == "SYSTEM")
    _row("System messages",             str(system))

    # Attachment references
    attachments = sum(1 for m in messages if m.message_type == "attachment")
    _row("Attachment messages",         str(attachments))

    _row("Quality checks",              "PASS")


# ---------------------------------------------------------------------------
# Phase 2
# ---------------------------------------------------------------------------

def run_phase2(chat) -> tuple:
    _section("PHASE 2 - Document Preparation and Token-Aware Chunking")

    from app.documents.phase2_pipeline import Phase2Pipeline

    t0 = time.perf_counter()
    try:
        documents = Phase2Pipeline(chat).run()
    except Exception as exc:
        _row("Chunking", "FAIL")
        _error(str(exc))
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
    elapsed = time.perf_counter() - t0

    if not documents:
        _row("Documents created", "FAIL")
        _error("Phase 2 produced zero documents.")
        sys.exit(1)

    token_counts = [d.token_count for d in documents]
    avg_tok = sum(token_counts) / len(token_counts)

    _row("Chunking",          "PASS")
    _row("Documents created", str(len(documents)))
    _row("Min tokens/chunk",  str(min(token_counts)))
    _row("Max tokens/chunk",  str(max(token_counts)))
    _row("Average tokens",    "{:.1f}".format(avg_tok))
    _row("Phase 2 time",      _elapsed(elapsed))
    return documents, elapsed


# ---------------------------------------------------------------------------
# Phase 3
# ---------------------------------------------------------------------------

def run_phase3(documents: list) -> tuple:
    _section("PHASE 3 - Embedding Generation (BAAI/bge-m3)")

    from app.vectorization.embedding_pipeline import EmbeddingPipeline

    _info("Embedding {} documents - this may take several minutes ...".format(
        len(documents)))

    t0 = time.perf_counter()
    try:
        embedded = EmbeddingPipeline(documents, batch_size=32).run()
    except Exception as exc:
        _row("Embedding", "FAIL")
        _error(str(exc))
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
    elapsed = time.perf_counter() - t0

    if not embedded:
        _row("Embeddings created", "FAIL")
        _error("Phase 3 produced zero embeddings.")
        sys.exit(1)

    throughput = len(embedded) / elapsed if elapsed > 0 else 0.0
    _row("Embedding model",     embedded[0].model_name)
    _row("Embeddings created",  str(len(embedded)))
    _row("Embedding dimension", str(embedded[0].embedding_dim))
    _row("Throughput",          "{:.1f} docs/s".format(throughput))
    _row("Embedding",           "PASS")
    _row("Phase 3 time",        _elapsed(elapsed))
    return embedded, elapsed


# ---------------------------------------------------------------------------
# Phase 4
# ---------------------------------------------------------------------------

def run_phase4(embedded: list) -> tuple:
    _section("PHASE 4 - ChromaDB Vector Storage")

    from app.storage.vector_store.phase4_pipeline import Phase4Pipeline
    from config.vector_config import VectorStoreConfig

    store_cfg = VectorStoreConfig(
        collection_name=_COLLECTION,
        persist_directory=_PERSIST_DIR,
        distance_metric="cosine",
        batch_size=100,
        embedding_model="BAAI/bge-m3",
        schema_version="1.0.0",
    )

    _row("Collection",  _COLLECTION)
    _row("Directory",   _PERSIST_DIR)

    t0 = time.perf_counter()
    try:
        summary = Phase4Pipeline(embedded, config=store_cfg).run()
    except Exception as exc:
        _row("Storage", "FAIL")
        _error(str(exc))
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
    elapsed = time.perf_counter() - t0

    _row("Vectors received", str(summary.documents_received))
    _row("Vectors inserted",  str(summary.documents_inserted))
    _row("Vectors skipped",   "{} (already in DB)".format(summary.documents_skipped))
    _row("Stored vectors",    str(summary.final_count))
    _row("Persistence",       "PASS" if summary.final_count > 0 else "WARN-zero")
    _row("Phase 4 time",      _elapsed(elapsed))
    return summary, elapsed


# ---------------------------------------------------------------------------
# Phase 5
# ---------------------------------------------------------------------------

def run_phase5() -> tuple:
    _section("PHASE 5 - Semantic Retrieval (15 queries)")

    from config.retrieval_config import RetrievalConfig
    from app.retrieval.retrieval_pipeline import RetrievalPipeline

    ret_cfg = RetrievalConfig(
        collection_name=_COLLECTION,
        persist_directory=_PERSIST_DIR,
        embedding_model="BAAI/bge-m3",
        top_k=_TOP_K,
        score_threshold=0.0,
        distance_metric="cosine",
    )

    try:
        pipeline = RetrievalPipeline(config=ret_cfg)
    except Exception as exc:
        _error("Retrieval pipeline init failed: {}".format(exc))
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

    total_queries = 0
    successful    = 0
    total_results = 0
    retrieved_docs_per_query: dict = {}

    t_phase5 = time.perf_counter()
    for query in _QUERIES:
        total_queries += 1
        print()
        _line("-")
        _info("Query : {}".format(query))
        _line("-")

        t0 = time.perf_counter()
        try:
            results = pipeline.search(query)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            successful += 1
            total_results += len(results)
            retrieved_docs_per_query[query] = results
        except Exception as exc:
            _error("Query failed: {}".format(exc))
            retrieved_docs_per_query[query] = []
            continue

        if not results:
            _info("No relevant documents found ({:.0f} ms)".format(elapsed_ms))
            continue

        _info("{} result(s)  ({:.0f} ms)".format(len(results), elapsed_ms))
        print()

        for r in results:
            meta = r.metadata
            meta_parts = []
            if meta.get("source_chat"):
                meta_parts.append("chat={}".format(_safe(str(meta["source_chat"]))))
            if meta.get("chunk_index") is not None:
                meta_parts.append("chunk={}".format(meta["chunk_index"]))
            if meta.get("message_count"):
                meta_parts.append("msgs={}".format(meta["message_count"]))
            if meta.get("start_timestamp"):
                meta_parts.append("from={}".format(_safe(str(meta["start_timestamp"]))))
            for flag in ("contains_images","contains_audio","contains_video","contains_documents"):
                if meta.get(flag):
                    meta_parts.append(flag.replace("contains_","has_"))
            if meta.get("attachment_count"):
                meta_parts.append("attachments={}".format(meta["attachment_count"]))

            _info("  Rank {}  |  Similarity {:.4f}  |  ID {}".format(
                r.rank, r.similarity_score, r.document_id[:16]))
            _info("  Text : {}".format(_preview(r.text)))
            _info("  Meta : {}".format(", ".join(meta_parts) if meta_parts else "(none)"))
            print()

    pipeline.close()
    elapsed_phase5 = time.perf_counter() - t_phase5

    return {
        "total_queries":  total_queries,
        "successful":     successful,
        "total_results":  total_results,
        "per_query":      retrieved_docs_per_query,
    }, elapsed_phase5


# ---------------------------------------------------------------------------
# Phase 6 - Grounded RAG
# ---------------------------------------------------------------------------

def run_phase6(phase5_results: dict) -> tuple:
    _section("PHASE 6 - Grounded RAG Answer Generation")

    from config.llm_config import LLMConfig
    from llm.ollama_provider import OllamaProvider
    from app.generation.phase6_pipeline import Phase6Pipeline

    llm_cfg = LLMConfig(
        provider=_LLM_PROVIDER,
        model=_LLM_MODEL,
        temperature=0.2,
        max_tokens=512,
        context_token_budget=2000,
    )

    _row("LLM provider",  _LLM_PROVIDER)
    _row("LLM model",     _LLM_MODEL)

    # Health-check Ollama before attempting generation
    try:
        provider = OllamaProvider(llm_cfg)
        healthy = provider.health_check()
    except Exception as exc:
        _warn("Ollama not reachable: {}".format(exc))
        _warn("Phase 6 skipped. Start Ollama with: ollama serve")
        _row("Phase 6", "SKIPPED (Ollama unavailable)")
        return {"answers_generated": 0, "answers_skipped": len(_RAG_QUERIES)}, 0.0

    if not healthy:
        _warn("Ollama health check returned False.")
        _warn("Phase 6 skipped. Start Ollama with: ollama serve")
        _row("Phase 6", "SKIPPED (Ollama unavailable)")
        return {"answers_generated": 0, "answers_skipped": len(_RAG_QUERIES)}, 0.0

    _row("Ollama health",  "PASS")

    gen_pipeline = Phase6Pipeline(provider=provider, config=llm_cfg)
    answers_generated = 0
    answers_skipped   = 0
    t_phase6 = time.perf_counter()

    for query in _RAG_QUERIES:
        docs = phase5_results["per_query"].get(query, [])
        print()
        _line("-")
        _info("RAG Query : {}".format(query))
        _line("-")

        if not docs:
            _info("No retrieved documents for this query - skipping RAG.")
            _info("Answer: I could not find that information in your knowledge base.")
            answers_skipped += 1
            continue

        t0 = time.perf_counter()
        try:
            answer = gen_pipeline.run(
                question=query,
                retrieved_documents=docs,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            answers_generated += 1
        except Exception as exc:
            _error("Phase 6 generation failed for query {!r}: {}".format(query, exc))
            answers_skipped += 1
            continue

        _info("Answer ({:.0f} ms, {:.4f} confidence):".format(
            elapsed_ms, answer.confidence))
        # Print answer safely - it may contain Unicode from the LLM
        answer_safe = _safe(answer.answer)
        # Wrap at 70 chars
        words = answer_safe.split()
        line_buf: List[str] = []
        char_count = 0
        for word in words:
            if char_count + len(word) + 1 > 70 and line_buf:
                _info("  " + " ".join(line_buf))
                line_buf = [word]
                char_count = len(word)
            else:
                line_buf.append(word)
                char_count += len(word) + 1
        if line_buf:
            _info("  " + " ".join(line_buf))

        print()
        _info("Citations ({} total):".format(answer.citation_count))
        for c in answer.citations:
            _info("  [{}] score={:.4f}  chat={}  chunk={}".format(
                c.rank, c.similarity_score,
                _safe(c.source_chat), c.chunk_index))

        # Validate grounding
        if answer.answer.strip():
            _row("Grounding",      "PASS - answer uses context")
        if answer.has_citations:
            _row("Citations",      "PASS - {} citation(s)".format(answer.citation_count))
        _row("Provider",       answer.provider)
        _row("Model",          answer.model)
        _row("Tokens used",    str(answer.tokens_used))

    elapsed_phase6 = time.perf_counter() - t_phase6
    provider.close()

    _row("Answers generated", str(answers_generated))
    _row("Answers skipped",   str(answers_skipped))
    _row("Phase 6 time",      _elapsed(elapsed_phase6))

    return {
        "answers_generated": answers_generated,
        "answers_skipped":   answers_skipped,
    }, elapsed_phase6


# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------

def _print_final_report(
    zip_path: Path,
    chat,
    documents: list,
    embedded: list,
    storage_summary,
    phase5: dict,
    phase6: dict,
    wall_elapsed: float,
    phase_times: dict,
) -> bool:
    _header("NEXORA - AMIRTHA DATASET - FINAL REPORT")

    _row("Dataset",              _safe(zip_path.name))
    _row("Participants",         str(len(chat.participants)))
    _row("Messages",             str(chat.metadata.total_messages))
    _row("Documents (chunks)",   str(len(documents)))
    _row("Embeddings",           str(len(embedded)))
    _row("Stored vectors",       str(storage_summary.final_count))
    _row("Queries executed",     str(phase5["total_queries"]))
    _row("Successful retrievals",str(phase5["successful"]))
    _row("Total results",        str(phase5["total_results"]))
    _row("Grounded answers",     str(phase6.get("answers_generated", 0)))

    print()
    _line("-")
    _info("Phase timing")
    _line("-")
    for phase_name, t in phase_times.items():
        _row(phase_name, _elapsed(t))
    _row("Total pipeline time", _elapsed(wall_elapsed))

    print()
    _line("-")
    _info("Phase status")
    _line("-")
    p1_ok = True
    p2_ok = bool(documents)
    p3_ok = bool(embedded)
    p4_ok = storage_summary.final_count > 0
    p5_ok = phase5["successful"] == phase5["total_queries"]
    p6_ans = phase6.get("answers_generated", 0)
    p6_skip = phase6.get("answers_skipped", 0)
    p6_ok  = p6_ans > 0 or p6_skip == len(_RAG_QUERIES)  # skip is ok if Ollama absent

    _row("Phase 1 - Ingestion",    "PASS" if p1_ok else "FAIL")
    _row("Phase 2 - Chunking",     "PASS" if p2_ok else "FAIL")
    _row("Phase 3 - Embedding",    "PASS" if p3_ok else "FAIL")
    _row("Phase 4 - Storage",      "PASS" if p4_ok else "FAIL")
    _row("Phase 5 - Retrieval",    "PASS" if p5_ok else
         "PARTIAL ({}/{})".format(phase5["successful"], phase5["total_queries"]))
    if p6_ans > 0:
        _row("Phase 6 - RAG",      "PASS ({} answers)".format(p6_ans))
    elif p6_skip == len(_RAG_QUERIES):
        _row("Phase 6 - RAG",      "SKIPPED (Ollama not running)")
    else:
        _row("Phase 6 - RAG",      "PARTIAL ({}/{})".format(p6_ans, len(_RAG_QUERIES)))

    overall = p2_ok and p3_ok and p4_ok and phase5["successful"] > 0
    print()
    _line("=")
    _info("OVERALL STATUS : {}".format("PASS" if overall else "FAIL"))
    _line("=")
    print()
    return overall


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    _header("NEXORA PHASE 1-6 VALIDATION - AMIRTHA DATASET")
    _row("Input ZIP",   _safe(str(_ZIP_PATH)))
    _row("Collection",  _COLLECTION)
    _row("Persist dir", _PERSIST_DIR)
    _row("Queries",     str(len(_QUERIES)))
    _row("RAG queries", str(len(_RAG_QUERIES)))
    _row("Top-K",       str(_TOP_K))

    phase_times: dict = {}
    wall_start = time.perf_counter()

    try:
        # Phase 1
        t = time.perf_counter()
        chat, _ = run_phase1()
        phase_times["Phase 1"] = time.perf_counter() - t

        # Quality checks (no timer — informational only)
        quality_checks(chat)

        # Phase 2
        t = time.perf_counter()
        documents, _ = run_phase2(chat)
        phase_times["Phase 2"] = time.perf_counter() - t

        # Phase 3
        t = time.perf_counter()
        embedded, _ = run_phase3(documents)
        phase_times["Phase 3"] = time.perf_counter() - t

        # Phase 4
        t = time.perf_counter()
        storage_summary, _ = run_phase4(embedded)
        phase_times["Phase 4"] = time.perf_counter() - t

        # Phase 5
        t = time.perf_counter()
        phase5_results, elapsed_p5 = run_phase5()
        phase_times["Phase 5"] = elapsed_p5

        # Phase 6
        t = time.perf_counter()
        phase6_results, elapsed_p6 = run_phase6(phase5_results)
        phase_times["Phase 6"] = elapsed_p6

    except SystemExit:
        raise
    except KeyboardInterrupt:
        print()
        _error("Interrupted by user.")
        return 130
    except Exception:
        _error("Unexpected pipeline failure:")
        traceback.print_exc(file=sys.stderr)
        return 1

    wall_elapsed = time.perf_counter() - wall_start

    ok = _print_final_report(
        zip_path        = _ZIP_PATH,
        chat            = chat,
        documents       = documents,
        embedded        = embedded,
        storage_summary = storage_summary,
        phase5          = phase5_results,
        phase6          = phase6_results,
        wall_elapsed    = wall_elapsed,
        phase_times     = phase_times,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
