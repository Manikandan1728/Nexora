"""
scripts/test_real_whatsapp_pipeline.py
======================================
Nexora developer integration console.

Runs Phase 1 through Phase 5 against a real WhatsApp ZIP export and
prints a structured plain-ASCII report to stdout.

Usage
-----
    python scripts/test_real_whatsapp_pipeline.py
    python scripts/test_real_whatsapp_pipeline.py "D:\\SomeOtherChat.zip"

All output uses plain ASCII only - safe on Windows PowerShell (cp1252)
and any Unicode terminal.

Rules
-----
  - No RAG, no LLM, no API, no UI.
  - Uses only existing Nexora pipeline classes.
  - Does not duplicate any business logic.
  - Does not modify any completed phase module.
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path
from typing import List


# ---------------------------------------------------------------------------
# Bootstrap: add the project root to sys.path before any Nexora imports
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Fixed configuration for this validation run
# ---------------------------------------------------------------------------
_DEFAULT_ZIP   = _PROJECT_ROOT / "WhatsApp Chat with Naveen Kumar.zip"
_COLLECTION    = "nexora_real_test"
_PERSIST_DIR   = str(_PROJECT_ROOT / "data" / "vectors" / "real_test")
_EXTRACT_ROOT  = str(_PROJECT_ROOT / "data" / "extracted")
_TOP_K         = 5
_PREVIEW_CHARS = 150

_QUERIES: List[str] = [
    "What files were shared?",
    "When were images shared?",
    "Show PDF related messages.",
    "What did Naveen talk about?",
    "Show messages about counselling.",
    "Did anyone share documents?",
    "Show attachment related discussion.",
    "When did we discuss project?",
]

# ---------------------------------------------------------------------------
# ASCII-only display helpers
# ---------------------------------------------------------------------------
_W = 60


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
    print("  {:<28} {}".format(label, value))


def _info(msg: str) -> None:
    print("  " + str(msg))


def _error(msg: str) -> None:
    print("  ERROR: " + str(msg), file=sys.stderr)


def _elapsed(seconds: float) -> str:
    if seconds < 60:
        return "{:.2f}s".format(seconds)
    m, s = divmod(int(seconds), 60)
    return "{}m {}s".format(m, s)


def _safe_ascii(text: str) -> str:
    """Replace non-ASCII bytes so cp1252 cannot choke on printed output."""
    return text.encode("ascii", errors="replace").decode("ascii")


def _preview(text: str) -> str:
    """First _PREVIEW_CHARS characters, newlines collapsed, ASCII-safe."""
    flat = text.replace("\n", " ").replace("\r", " ").strip()
    flat = _safe_ascii(flat)
    if len(flat) > _PREVIEW_CHARS:
        return flat[:_PREVIEW_CHARS] + "..."
    return flat


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="test_real_whatsapp_pipeline",
        description="Nexora end-to-end developer validation console (Phase 1-5).",
    )
    parser.add_argument(
        "zip_path",
        nargs="?",
        default=str(_DEFAULT_ZIP),
        help=(
            "Path to the WhatsApp export ZIP. "
            "Defaults to: {}".format(_DEFAULT_ZIP)
        ),
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Phase 1 - Ingestion
# ---------------------------------------------------------------------------

def run_phase1(zip_path: Path) -> object:
    _section("PHASE 1 - WhatsApp Ingestion and Parsing")

    from pipeline.phase1_pipeline import Phase1Pipeline

    if not zip_path.exists():
        _row("ZIP found", "FAIL")
        _error("File not found: {}".format(zip_path))
        _error("Place the WhatsApp export ZIP at that path and re-run.")
        sys.exit(1)

    _row("ZIP found", "PASS")

    t0 = time.perf_counter()
    try:
        p1 = Phase1Pipeline(
            input_path=str(zip_path),
            extract_root=_EXTRACT_ROOT,
        )
        chat = p1.run()
    except Exception as exc:
        _row("ZIP validation", "FAIL")
        _error(str(exc))
        sys.exit(1)

    elapsed = time.perf_counter() - t0

    _row("ZIP validation",  "PASS")
    _row("Extraction",      "PASS")
    _row("Messages parsed", str(chat.metadata.total_messages))
    _row("Participants",    str(len(chat.participants)))
    _row("Names",           _safe_ascii(", ".join(chat.participants)))
    _row("Attachments",     str(chat.metadata.attachment_count))
    _row("Date start",      _safe_ascii(chat.metadata.chat_start_date))
    _row("Date end",        _safe_ascii(chat.metadata.chat_end_date))
    _row("Metadata",        "PASS")
    _row("Phase 1 time",    _elapsed(elapsed))
    return chat


# ---------------------------------------------------------------------------
# Phase 2 - Chunking
# ---------------------------------------------------------------------------

def run_phase2(chat) -> list:
    _section("PHASE 2 - Document Preparation and Chunking")

    from app.documents.phase2_pipeline import Phase2Pipeline

    t0 = time.perf_counter()
    try:
        documents = Phase2Pipeline(chat).run()
    except Exception as exc:
        _row("Chunking", "FAIL")
        _error(str(exc))
        sys.exit(1)

    elapsed = time.perf_counter() - t0

    if not documents:
        _row("Documents created", "FAIL")
        _error("Phase 2 produced zero documents.")
        sys.exit(1)

    token_counts = [d.token_count for d in documents]
    avg_tokens = sum(token_counts) / len(token_counts)

    _row("Chunking",          "PASS")
    _row("Documents created", str(len(documents)))
    _row("Min tokens/chunk",  str(min(token_counts)))
    _row("Max tokens/chunk",  str(max(token_counts)))
    _row("Average tokens",    "{:.1f}".format(avg_tokens))
    _row("Phase 2 time",      _elapsed(elapsed))
    return documents


# ---------------------------------------------------------------------------
# Phase 3 - Embedding
# ---------------------------------------------------------------------------

def run_phase3(documents: list) -> list:
    _section("PHASE 3 - Embedding Generation (BAAI/bge-m3)")

    from app.vectorization.embedding_pipeline import EmbeddingPipeline

    _info("Embedding {} documents - this may take several minutes ...".format(
        len(documents)
    ))

    t0 = time.perf_counter()
    try:
        embedded = EmbeddingPipeline(documents, batch_size=32).run()
    except Exception as exc:
        _row("Embedding", "FAIL")
        _error(str(exc))
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
    return embedded


# ---------------------------------------------------------------------------
# Phase 4 - Vector storage
# ---------------------------------------------------------------------------

def run_phase4(embedded: list) -> object:
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
        sys.exit(1)

    elapsed = time.perf_counter() - t0

    persist_status = "PASS" if summary.final_count > 0 else "WARN-zero vectors"

    _row("Vectors received",  str(summary.documents_received))
    _row("Vectors inserted",  str(summary.documents_inserted))
    _row("Vectors skipped",   "{} (already in DB)".format(summary.documents_skipped))
    _row("Stored vectors",    str(summary.final_count))
    _row("Persistence",       persist_status)
    _row("Phase 4 time",      _elapsed(elapsed))
    return summary


# ---------------------------------------------------------------------------
# Phase 5 - Semantic Retrieval
# ---------------------------------------------------------------------------

def run_phase5() -> dict:
    _section("PHASE 5 - Semantic Retrieval Tests")

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

    _info("Initialising retrieval pipeline ...")
    try:
        pipeline = RetrievalPipeline(config=ret_cfg)
    except Exception as exc:
        _error("Failed to initialise retrieval pipeline: {}".format(exc))
        sys.exit(1)

    total_queries  = 0
    successful     = 0
    total_results  = 0

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
        except Exception as exc:
            _error("Query failed: {}".format(exc))
            continue

        if not results:
            _info("No results returned ({:.0f} ms)".format(elapsed_ms))
            continue

        _info("{} result(s)  ({:.0f} ms)".format(len(results), elapsed_ms))
        print()

        for r in results:
            preview = _preview(r.text)
            meta = r.metadata

            meta_parts = []
            if meta.get("source_chat"):
                meta_parts.append(
                    "chat={}".format(_safe_ascii(str(meta["source_chat"])))
                )
            if meta.get("chunk_index") is not None:
                meta_parts.append("chunk={}".format(meta["chunk_index"]))
            if meta.get("message_count"):
                meta_parts.append("msgs={}".format(meta["message_count"]))
            if meta.get("start_timestamp"):
                meta_parts.append(
                    "from={}".format(_safe_ascii(str(meta["start_timestamp"])))
                )
            if meta.get("end_timestamp"):
                meta_parts.append(
                    "to={}".format(_safe_ascii(str(meta["end_timestamp"])))
                )
            for flag in (
                "contains_images", "contains_audio",
                "contains_video", "contains_documents",
            ):
                if meta.get(flag):
                    meta_parts.append(flag.replace("contains_", "has_"))
            if meta.get("attachment_count"):
                meta_parts.append("attachments={}".format(meta["attachment_count"]))

            doc_short = r.document_id[:16]
            _info("  Rank {}  |  Similarity {:.4f}  |  ID {}".format(
                r.rank, r.similarity_score, doc_short
            ))
            _info("  Text    : {}".format(preview))
            _info("  Meta    : {}".format(
                ", ".join(meta_parts) if meta_parts else "(none)"
            ))
            print()

    pipeline.close()

    return {
        "total_queries": total_queries,
        "successful":    successful,
        "total_results": total_results,
    }


# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------

def _print_summary(
    zip_path: Path,
    chat,
    documents: list,
    embedded: list,
    storage_summary,
    phase5: dict,
    wall_elapsed: float,
    phase_times: dict,
) -> bool:
    _header("NEXORA - FINAL REPORT")

    _row("Dataset",             _safe_ascii(zip_path.name))
    _row("Messages",            str(chat.metadata.total_messages))
    _row("Participants",        str(len(chat.participants)))
    _row("Documents",           str(len(documents)))
    _row("Embeddings",          str(len(embedded)))
    _row("Stored vectors",      str(storage_summary.final_count))
    _row("Queries executed",    str(phase5["total_queries"]))
    _row("Successful queries",  str(phase5["successful"]))
    _row("Total results",       str(phase5["total_results"]))

    print()
    _line("-")
    _info("Phase timing")
    _line("-")
    for phase, t in phase_times.items():
        _row(phase, _elapsed(t))
    _row("Total pipeline time", _elapsed(wall_elapsed))

    print()
    _line("-")
    _info("Phase status")
    _line("-")
    p2_ok = bool(documents)
    p3_ok = bool(embedded)
    p4_ok = storage_summary.final_count > 0
    p5_ok = phase5["successful"] == phase5["total_queries"]

    _row("Phase 1", "PASS")
    _row("Phase 2", "PASS" if p2_ok else "FAIL")
    _row("Phase 3", "PASS" if p3_ok else "FAIL")
    _row("Phase 4", "PASS" if p4_ok else "FAIL")
    _row("Phase 5", "PASS" if p5_ok else
         "PARTIAL ({}/{})".format(phase5["successful"], phase5["total_queries"]))

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
    args     = _parse_args()
    zip_path = Path(args.zip_path).resolve()

    _header("NEXORA REAL DATASET VALIDATION")
    _row("Input ZIP",   _safe_ascii(str(zip_path)))
    _row("Collection",  _COLLECTION)
    _row("Persist dir", _PERSIST_DIR)
    _row("Queries",     str(len(_QUERIES)))
    _row("Top-K",       str(_TOP_K))

    phase_times: dict = {}
    wall_start  = time.perf_counter()

    try:
        t = time.perf_counter()
        chat = run_phase1(zip_path)
        phase_times["Phase 1"] = time.perf_counter() - t

        t = time.perf_counter()
        documents = run_phase2(chat)
        phase_times["Phase 2"] = time.perf_counter() - t

        t = time.perf_counter()
        embedded = run_phase3(documents)
        phase_times["Phase 3"] = time.perf_counter() - t

        t = time.perf_counter()
        storage_summary = run_phase4(embedded)
        phase_times["Phase 4"] = time.perf_counter() - t

        t = time.perf_counter()
        phase5 = run_phase5()
        phase_times["Phase 5"] = time.perf_counter() - t

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

    ok = _print_summary(
        zip_path        = zip_path,
        chat            = chat,
        documents       = documents,
        embedded        = embedded,
        storage_summary = storage_summary,
        phase5          = phase5,
        wall_elapsed    = wall_elapsed,
        phase_times     = phase_times,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
