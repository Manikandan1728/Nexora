"""
scripts/validate_all_datasets.py
=================================
Auto-discovers every WhatsApp ZIP in the project root, skips datasets
that were already validated in previous runs, and executes the full
Nexora Phase 1-6 pipeline against each remaining dataset.

Produces:
  - Per-dataset console output (ASCII-safe)
  - docs/validation_report.md  (Markdown summary)

Usage
-----
    python scripts/validate_all_datasets.py

Rules
-----
  - No production code is modified.
  - No new features are added.
  - Existing ChromaDB collections are never overwritten.
  - Phase 6 is skipped gracefully when Ollama is unavailable.
  - If a dataset fails, validation continues for the remaining ones.
"""

from __future__ import annotations

import re
import sys
import time
import traceback
from pathlib import Path
from typing import List, Dict, Optional

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Datasets already validated in previous runs — skip these
# ---------------------------------------------------------------------------
_ALREADY_VALIDATED = {
    "whatsapp chat with naveen kumar.zip",
    "whatsapp chat with amirtha.zip",
    "whatsapp chat with annie.zip",
    "whatsapp chat with data sorcerers.zip",
    "whatsapp chat with janani.zip",
}

# ---------------------------------------------------------------------------
# Static query list (20 semantic queries)
# ---------------------------------------------------------------------------
_QUERIES: List[str] = [
    "What files were shared?",
    "What documents were shared?",
    "When were images shared?",
    "Show assignment discussions.",
    "Show exam discussions.",
    "Show project discussions.",
    "Show college-related messages.",
    "Did anyone share links?",
    "Show PPT related messages.",
    "Show PDF related messages.",
    "Show voice message references.",
    "Show important reminders.",
    "What did Dharshini ask?",
    "Show submission-related messages.",
    "Show internship or placement discussions.",
    "Show seminar discussions.",
    "Show AI-related discussions.",
    "Show messages about deadlines.",
    "Show deleted message references.",
    "Show important conversations.",
]

_TOP_K = 5
_RAG_QUERIES: List[str] = [
    "What files were shared?",
    "Show assignment discussions.",
    "Show project discussions.",
]
_LLM_PROVIDER = "ollama"
_LLM_MODEL    = "llama3"

# ---------------------------------------------------------------------------
# ASCII helpers
# ---------------------------------------------------------------------------
_W = 64

def _line(c: str = "-") -> None:
    print(c * _W)

def _header(t: str) -> None:
    print(); _line("="); print(t); _line("=")

def _section(t: str) -> None:
    print(); _line("-"); print(t); _line("-")

def _row(label: str, value: str) -> None:
    print("  {:<30} {}".format(label, str(value)))

def _info(msg: str) -> None:
    print("  " + str(msg))

def _warn(msg: str) -> None:
    print("  WARN: " + str(msg))

def _err(msg: str) -> None:
    print("  ERROR: " + str(msg), file=sys.stderr)

def _elapsed(s: float) -> str:
    if s < 60:
        return "{:.2f}s".format(s)
    m, sec = divmod(int(s), 60)
    return "{}m {}s".format(m, sec)

def _safe(text: str) -> str:
    return text.encode("ascii", errors="replace").decode("ascii")

def _preview(text: str, n: int = 130) -> str:
    flat = text.replace("\n", " ").replace("\r", " ").strip()
    flat = _safe(flat)
    return flat[:n] + "..." if len(flat) > n else flat

def _slug(name: str) -> str:
    """Convert a ZIP filename to a safe ChromaDB collection name."""
    stem = Path(name).stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
    return "nexora_val_{}".format(slug[:40])

# ---------------------------------------------------------------------------
# Discover ZIPs
# ---------------------------------------------------------------------------

def discover_zips() -> List[Path]:
    zips = sorted(_PROJECT_ROOT.glob("*.zip"))
    remaining = [
        z for z in zips
        if z.name.lower() not in _ALREADY_VALIDATED
    ]
    return remaining


# ---------------------------------------------------------------------------
# Phase runners — each returns a result dict or raises
# ---------------------------------------------------------------------------

def phase1(zip_path: Path, extract_root: str) -> dict:
    from pipeline.phase1_pipeline import Phase1Pipeline
    t0 = time.perf_counter()
    chat = Phase1Pipeline(
        input_path=str(zip_path),
        extract_root=extract_root,
    ).run()
    elapsed = time.perf_counter() - t0

    messages = chat.messages
    non_ascii = sum(1 for m in messages if any(ord(c) > 127 for c in m.message))
    tamil     = sum(1 for m in messages if any(0x0B80 <= ord(c) <= 0x0BFF for c in m.message))
    deleted   = sum(1 for m in messages if "this message was deleted" in m.message.lower())
    system_   = sum(1 for m in messages if m.sender == "SYSTEM")
    attach    = sum(1 for m in messages if m.message_type == "attachment")

    return {
        "chat":            chat,
        "messages":        chat.metadata.total_messages,
        "participants":    chat.participants,
        "attachments":     chat.metadata.attachment_count,
        "date_start":      chat.metadata.chat_start_date,
        "date_end":        chat.metadata.chat_end_date,
        "non_ascii":       non_ascii,
        "tamil":           tamil,
        "deleted":         deleted,
        "system_msgs":     system_,
        "attach_msgs":     attach,
        "elapsed":         elapsed,
    }


def phase2(chat) -> dict:
    from app.documents.phase2_pipeline import Phase2Pipeline
    t0 = time.perf_counter()
    documents = Phase2Pipeline(chat).run()
    elapsed   = time.perf_counter() - t0
    token_counts = [d.token_count for d in documents]
    return {
        "documents": documents,
        "count":     len(documents),
        "min_tok":   min(token_counts) if token_counts else 0,
        "max_tok":   max(token_counts) if token_counts else 0,
        "avg_tok":   sum(token_counts) / len(token_counts) if token_counts else 0.0,
        "elapsed":   elapsed,
    }


def phase3(documents: list) -> dict:
    from app.vectorization.embedding_pipeline import EmbeddingPipeline
    t0 = time.perf_counter()
    embedded = EmbeddingPipeline(documents, batch_size=32).run()
    elapsed  = time.perf_counter() - t0
    return {
        "embedded":  embedded,
        "count":     len(embedded),
        "dim":       embedded[0].embedding_dim if embedded else 0,
        "model":     embedded[0].model_name    if embedded else "N/A",
        "elapsed":   elapsed,
    }


def phase4(embedded: list, collection: str, persist_dir: str) -> dict:
    from app.storage.vector_store.phase4_pipeline import Phase4Pipeline
    from config.vector_config import VectorStoreConfig
    cfg = VectorStoreConfig(
        collection_name=collection,
        persist_directory=persist_dir,
        distance_metric="cosine",
        batch_size=100,
        embedding_model="BAAI/bge-m3",
        schema_version="1.0.0",
    )
    t0 = time.perf_counter()
    summary = Phase4Pipeline(embedded, config=cfg).run()
    elapsed = time.perf_counter() - t0
    return {
        "summary":    summary,
        "inserted":   summary.documents_inserted,
        "final":      summary.final_count,
        "skipped":    summary.documents_skipped,
        "elapsed":    elapsed,
    }


def phase5(collection: str, persist_dir: str) -> dict:
    from config.retrieval_config import RetrievalConfig
    from app.retrieval.retrieval_pipeline import RetrievalPipeline
    cfg = RetrievalConfig(
        collection_name=collection,
        persist_directory=persist_dir,
        embedding_model="BAAI/bge-m3",
        top_k=_TOP_K,
        score_threshold=0.0,
        distance_metric="cosine",
    )
    pipeline = RetrievalPipeline(config=cfg)
    total = successful = total_results = 0
    per_query: Dict[str, list] = {}
    t0 = time.perf_counter()

    for query in _QUERIES:
        total += 1
        try:
            results = pipeline.search(query)
            successful += 1
            total_results += len(results)
            per_query[query] = results
        except Exception as exc:
            _warn("Query failed: {} — {}".format(query, exc))
            per_query[query] = []

    pipeline.close()
    elapsed = time.perf_counter() - t0
    return {
        "total_queries":  total,
        "successful":     successful,
        "total_results":  total_results,
        "per_query":      per_query,
        "elapsed":        elapsed,
    }


def phase6(p5: dict) -> dict:
    from config.llm_config import LLMConfig
    from llm.ollama_provider import OllamaProvider
    from app.generation.phase6_pipeline import Phase6Pipeline
    from exceptions.exceptions import LLMProviderError

    cfg = LLMConfig(
        provider=_LLM_PROVIDER,
        model=_LLM_MODEL,
        temperature=0.2,
        max_tokens=512,
        context_token_budget=2000,
    )
    try:
        provider = OllamaProvider(cfg)
        healthy  = provider.health_check()
    except Exception as exc:
        return {"status": "SKIPPED", "reason": str(exc), "generated": 0, "elapsed": 0.0}

    if not healthy:
        return {"status": "SKIPPED", "reason": "Ollama not running", "generated": 0, "elapsed": 0.0}

    gen_pipeline = Phase6Pipeline(provider=provider, config=cfg)
    generated = skipped = 0
    t0 = time.perf_counter()

    for query in _RAG_QUERIES:
        docs = p5["per_query"].get(query, [])
        if not docs:
            skipped += 1
            continue
        try:
            answer    = gen_pipeline.run(question=query, retrieved_documents=docs)
            generated += 1
        except Exception as exc:
            _warn("RAG failed for {!r}: {}".format(query, exc))
            skipped += 1

    provider.close()
    elapsed = time.perf_counter() - t0
    status  = "PASS" if generated > 0 else "SKIPPED"
    return {"status": status, "generated": generated, "skipped": skipped, "elapsed": elapsed}


# ---------------------------------------------------------------------------
# Validate one dataset — returns a result dict regardless of failure
# ---------------------------------------------------------------------------

def validate_dataset(zip_path: Path) -> dict:
    name       = zip_path.name
    size_mb    = round(zip_path.stat().st_size / (1024 * 1024), 1)
    collection = _slug(name)
    persist    = str(_PROJECT_ROOT / "data" / "vectors" / collection)
    extract    = str(_PROJECT_ROOT / "data" / "extracted")

    _header("DATASET: {}".format(_safe(name)))
    _row("Size",       "{} MB".format(size_mb))
    _row("Collection", collection)
    _row("Persist",    persist)

    result: dict = {
        "name":       name,
        "size_mb":    size_mb,
        "collection": collection,
        "status":     "FAIL",
        "phases":     {},
        "wall":       0.0,
    }
    wall_start = time.perf_counter()

    # ── Phase 1 ──────────────────────────────────────────────────────
    _section("PHASE 1 - Ingestion")
    try:
        r1 = phase1(zip_path, extract)
        _row("Messages",    str(r1["messages"]))
        _row("Participants",str(len(r1["participants"])))
        _row("Names",       _safe(", ".join(r1["participants"])))
        _row("Attachments", str(r1["attachments"]))
        _row("Date start",  _safe(r1["date_start"]))
        _row("Date end",    _safe(r1["date_end"]))
        _row("Unicode/emoji msgs", str(r1["non_ascii"]))
        _row("Tamil msgs",  str(r1["tamil"]))
        _row("Deleted refs",str(r1["deleted"]))
        _row("System msgs", str(r1["system_msgs"]))
        _row("Attach msgs", str(r1["attach_msgs"]))
        _row("Phase 1",     "PASS  ({})".format(_elapsed(r1["elapsed"])))
        result["phases"]["p1"] = {"status": "PASS", **r1}
    except Exception as exc:
        _err("Phase 1 FAILED: {}".format(exc))
        traceback.print_exc(file=sys.stderr)
        result["phases"]["p1"] = {"status": "FAIL", "error": str(exc)}
        result["wall"] = time.perf_counter() - wall_start
        return result

    # ── Phase 2 ──────────────────────────────────────────────────────
    _section("PHASE 2 - Chunking")
    _info("Processing {} messages ...".format(r1["messages"]))
    try:
        r2 = phase2(r1["chat"])
        _row("Documents",   str(r2["count"]))
        _row("Min tokens",  str(r2["min_tok"]))
        _row("Max tokens",  str(r2["max_tok"]))
        _row("Avg tokens",  "{:.1f}".format(r2["avg_tok"]))
        _row("Phase 2",     "PASS  ({})".format(_elapsed(r2["elapsed"])))
        result["phases"]["p2"] = {"status": "PASS", **r2}
    except Exception as exc:
        _err("Phase 2 FAILED: {}".format(exc))
        traceback.print_exc(file=sys.stderr)
        result["phases"]["p2"] = {"status": "FAIL", "error": str(exc)}
        result["wall"] = time.perf_counter() - wall_start
        return result

    # ── Phase 3 ──────────────────────────────────────────────────────
    _section("PHASE 3 - Embedding (BAAI/bge-m3)")
    _info("Embedding {} documents — may take several minutes ...".format(r2["count"]))
    try:
        r3 = phase3(r2["documents"])
        _row("Embeddings",  str(r3["count"]))
        _row("Dimension",   str(r3["dim"]))
        _row("Model",       r3["model"])
        tput = r3["count"] / r3["elapsed"] if r3["elapsed"] > 0 else 0
        _row("Throughput",  "{:.1f} docs/s".format(tput))
        _row("Phase 3",     "PASS  ({})".format(_elapsed(r3["elapsed"])))
        result["phases"]["p3"] = {"status": "PASS", **r3}
    except Exception as exc:
        _err("Phase 3 FAILED: {}".format(exc))
        traceback.print_exc(file=sys.stderr)
        result["phases"]["p3"] = {"status": "FAIL", "error": str(exc)}
        result["wall"] = time.perf_counter() - wall_start
        return result

    # ── Phase 4 ──────────────────────────────────────────────────────
    _section("PHASE 4 - ChromaDB Storage")
    _row("Collection", collection)
    _row("Directory",  persist)
    try:
        r4 = phase4(r3["embedded"], collection, persist)
        _row("Received",  str(r4["summary"].documents_received))
        _row("Inserted",  str(r4["inserted"]))
        _row("Skipped",   str(r4["skipped"]))
        _row("Total",     str(r4["final"]))
        _row("Phase 4",   "PASS  ({})".format(_elapsed(r4["elapsed"])))
        result["phases"]["p4"] = {"status": "PASS", **r4}
    except Exception as exc:
        _err("Phase 4 FAILED: {}".format(exc))
        traceback.print_exc(file=sys.stderr)
        result["phases"]["p4"] = {"status": "FAIL", "error": str(exc)}
        result["wall"] = time.perf_counter() - wall_start
        return result

    # ── Phase 5 ──────────────────────────────────────────────────────
    _section("PHASE 5 - Semantic Retrieval ({} queries)".format(len(_QUERIES)))
    try:
        r5 = phase5(collection, persist)
        # Print per-query results compactly
        for query, docs in r5["per_query"].items():
            print()
            _info("Q: {}".format(query))
            if not docs:
                _info("  -> No relevant documents found")
            else:
                for d in docs[:2]:   # show top 2 per query to keep output manageable
                    _info("  [{}] {:.4f}  {}".format(
                        d.rank, d.similarity_score, _preview(d.text, 90)))

        _row("Queries run",  str(r5["total_queries"]))
        _row("Successful",   str(r5["successful"]))
        _row("Total results",str(r5["total_results"]))
        _row("Phase 5",      "PASS  ({})".format(_elapsed(r5["elapsed"])))
        result["phases"]["p5"] = {"status": "PASS", **r5}
    except Exception as exc:
        _err("Phase 5 FAILED: {}".format(exc))
        traceback.print_exc(file=sys.stderr)
        result["phases"]["p5"] = {"status": "FAIL", "error": str(exc)}
        result["wall"] = time.perf_counter() - wall_start
        return result

    # ── Phase 6 ──────────────────────────────────────────────────────
    _section("PHASE 6 - Grounded RAG")
    try:
        r6 = phase6(r5)
        _row("Status",      r6["status"])
        if r6["status"] != "SKIPPED":
            _row("Generated", str(r6["generated"]))
        else:
            _row("Reason",    r6.get("reason", ""))
        _row("Phase 6",     "{} ({})".format(r6["status"], _elapsed(r6.get("elapsed", 0.0))))
        result["phases"]["p6"] = {"status": r6["status"], **r6}
    except Exception as exc:
        _warn("Phase 6 error (non-fatal): {}".format(exc))
        result["phases"]["p6"] = {"status": "ERROR", "error": str(exc)}

    result["wall"]   = time.perf_counter() - wall_start
    result["status"] = "PASS"
    _header("RESULT: {}  ->  PASS  ({})".format(_safe(name), _elapsed(result["wall"])))
    return result


# ---------------------------------------------------------------------------
# Markdown report writer
# ---------------------------------------------------------------------------

def write_report(results: List[dict]) -> None:
    report_path = _PROJECT_ROOT / "docs" / "validation_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    # If a report already exists, append new sections and a new benchmark row.
    # Strip the old footer/benchmark so we can add a combined one.
    existing_content = ""
    if report_path.exists():
        raw = report_path.read_text(encoding="utf-8")
        # Remove everything from "## Benchmark Comparison" onwards
        cut = raw.find("\n## Benchmark Comparison")
        if cut != -1:
            existing_content = raw[:cut].rstrip() + "\n\n"
        else:
            # No benchmark section yet — keep everything, append below
            existing_content = raw.rstrip() + "\n\n"
    else:
        existing_content = (
            "# Nexora — Multi-Dataset Validation Report\n\n"
            "Generated automatically by `scripts/validate_all_datasets.py`.\n\n"
            "---\n\n"
            "## Per-Dataset Results\n\n"
        )

    new_sections: List[str] = []

    for r in results:
        p1 = r["phases"].get("p1", {})
        p2 = r["phases"].get("p2", {})
        p3 = r["phases"].get("p3", {})
        p4 = r["phases"].get("p4", {})
        p5 = r["phases"].get("p5", {})
        p6 = r["phases"].get("p6", {})

        new_sections += [
            "### {}".format(r["name"]),
            "",
            "| Field | Value |",
            "|---|---|",
            "| ZIP size | {} MB |".format(r["size_mb"]),
            "| Collection | `{}` |".format(r["collection"]),
            "| Participants | {} |".format(len(p1.get("participants", []))),
            "| Messages | {} |".format(p1.get("messages", "N/A")),
            "| Date range | {} to {} |".format(
                p1.get("date_start", "N/A"), p1.get("date_end", "N/A")),
            "| Unicode/emoji messages | {} |".format(p1.get("non_ascii", "N/A")),
            "| Tamil script messages | {} |".format(p1.get("tamil", "N/A")),
            "| Deleted refs | {} |".format(p1.get("deleted", "N/A")),
            "| System messages | {} |".format(p1.get("system_msgs", "N/A")),
            "| Attachment messages | {} |".format(p1.get("attach_msgs", "N/A")),
            "| Documents (chunks) | {} |".format(p2.get("count", "N/A")),
            "| Avg tokens/chunk | {:.1f} |".format(p2.get("avg_tok", 0.0)),
            "| Embeddings | {} |".format(p3.get("count", "N/A")),
            "| Embedding dimension | {} |".format(p3.get("dim", "N/A")),
            "| Stored vectors | {} |".format(p4.get("final", "N/A")),
            "| Queries executed | {} |".format(p5.get("total_queries", "N/A")),
            "| Successful retrievals | {} |".format(p5.get("successful", "N/A")),
            "| Total results returned | {} |".format(p5.get("total_results", "N/A")),
            "| Phase 6 status | {} |".format(p6.get("status", "N/A")),
            "| Total time | {} |".format(_elapsed(r["wall"])),
            "| **Overall** | **{}** |".format(r["status"]),
            "",
        ]

    # Rebuild benchmark section by re-parsing all existing per-dataset tables
    # (we preserved them above in existing_content) plus new results.
    # Simpler: just append a new benchmark row for each new result.
    # Read the old benchmark rows from the original file if it existed.
    old_benchmark_rows: List[str] = []
    if report_path.exists():
        original = report_path.read_text(encoding="utf-8")
        in_bench = False
        for line in original.splitlines():
            if line.startswith("| Dataset |"):
                in_bench = True
                continue
            if line.startswith("|---"):
                continue
            if in_bench and line.startswith("|"):
                old_benchmark_rows.append(line)
            elif in_bench and not line.startswith("|"):
                in_bench = False

    new_benchmark_rows: List[str] = []
    for r in results:
        p1 = r["phases"].get("p1", {})
        p2 = r["phases"].get("p2", {})
        p3 = r["phases"].get("p3", {})
        p5 = r["phases"].get("p5", {})
        p6 = r["phases"].get("p6", {})
        new_benchmark_rows.append("| {} | {} MB | {} | {} | {} | {}/{} | {} | {} | {} |".format(
            r["name"].replace("|", "-"),
            r["size_mb"],
            p1.get("messages", "-"),
            p2.get("count", "-"),
            p3.get("count", "-"),
            p5.get("successful", "-"), p5.get("total_queries", "-"),
            p6.get("status", "-"),
            _elapsed(r["wall"]),
            r["status"],
        ))

    benchmark_lines = [
        "## Benchmark Comparison",
        "",
        "| Dataset | Size | Messages | Chunks | Embeddings | Retrieval | Phase 6 | Time | Status |",
        "|---|---|---|---|---|---|---|---|---|",
    ] + old_benchmark_rows + new_benchmark_rows + [
        "",
        "---",
        "",
        "_Nexora validation suite — all phases tested, no production code modified._",
        "",
    ]

    final = (
        existing_content
        + "\n".join(new_sections)
        + "\n---\n\n"
        + "\n".join(benchmark_lines)
    )
    report_path.write_text(final, encoding="utf-8")
    print()
    _info("Validation report updated: {}".format(report_path))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    zips = discover_zips()

    _header("NEXORA MULTI-DATASET VALIDATION")
    _row("Datasets to validate", str(len(zips)))
    _row("Skipped (validated)",  str(len(_ALREADY_VALIDATED)))
    _row("Queries per dataset",  str(len(_QUERIES)))
    _row("RAG queries",          str(len(_RAG_QUERIES)))
    for z in zips:
        _info("  {}  ({} MB)".format(
            _safe(z.name),
            round(z.stat().st_size / (1024 * 1024), 1)))

    if not zips:
        _info("No new datasets to validate.")
        return 0

    all_results: List[dict] = []
    grand_start = time.perf_counter()

    for zip_path in zips:
        try:
            result = validate_dataset(zip_path)
        except Exception as exc:
            _err("Unhandled error for {}: {}".format(zip_path.name, exc))
            traceback.print_exc(file=sys.stderr)
            result = {
                "name": zip_path.name,
                "size_mb": round(zip_path.stat().st_size / (1024 * 1024), 1),
                "collection": _slug(zip_path.name),
                "status": "FAIL",
                "phases": {},
                "wall": 0.0,
            }
        all_results.append(result)

    grand_elapsed = time.perf_counter() - grand_start

    # Final console summary
    _header("FINAL MULTI-DATASET SUMMARY")
    _row("Total datasets",    str(len(all_results)))
    _row("Total time",        _elapsed(grand_elapsed))
    print()
    for r in all_results:
        _row(_safe(r["name"]), r["status"] + "  ({})".format(_elapsed(r["wall"])))

    write_report(all_results)

    passed = sum(1 for r in all_results if r["status"] == "PASS")
    failed = len(all_results) - passed
    print()
    _line("=")
    _info("PASSED: {}   FAILED: {}".format(passed, failed))
    _line("=")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
