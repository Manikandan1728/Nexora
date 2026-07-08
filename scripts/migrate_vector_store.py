"""
scripts/migrate_vector_store.py
================================
Milestone 2 — Historical vector database migration.

Migrates every per-collection ChromaDB database that was created by the
pre-Milestone-1 storage architecture into the single shared PersistentClient
at ``data/vectors/``.

Background
----------
Before Milestone 1, ``upload_service.py`` computed::

    persist_directory = data/vectors/<collection_name>

This created one isolated SQLite database per collection inside a
subdirectory.  The FastAPI layer (``collection_service``, ``query_service``)
correctly opens a single PersistentClient at ``data/vectors/`` and therefore
could not see any of those collections.

Milestone 1 fixed future uploads.  This script migrates the historical data.

Safety guarantees
-----------------
- Old databases are NEVER deleted, modified, or renamed.
- The script is fully idempotent: running it twice never duplicates vectors.
- If a count mismatch is detected after insertion the script stops and prints
  a detailed error.  No partial state is silently accepted.
- All reads from old databases; all writes to the shared root database.

Usage
-----
    python scripts/migrate_vector_store.py

    # Dry run (inspect without writing):
    python scripts/migrate_vector_store.py --dry-run

    # Custom vectors root (for testing):
    python scripts/migrate_vector_store.py --vectors-root /path/to/vectors
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import chromadb

# ---------------------------------------------------------------------------
# Bootstrap: ensure project root is on sys.path for any future imports
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("nexora.migrate")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_VECTORS_ROOT = _PROJECT_ROOT / "data" / "vectors"
_BATCH_SIZE = 100   # vectors per insertion batch (memory efficiency)
_COL_WIDTH  = 50    # report column width


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CollectionResult:
    """Result of migrating one collection."""

    source_dir: str
    collection_name: str
    old_count: int
    new_count_before: int   # vectors already in root before migration
    inserted: int           # vectors actually written
    status: str             # "MIGRATED" | "SKIPPED" | "FAILED" | "DRY_RUN"
    error: Optional[str] = None


@dataclass
class MigrationSummary:
    """Aggregated results across all collections."""

    collections: List[CollectionResult] = field(default_factory=list)

    @property
    def total_old(self) -> int:
        return sum(r.old_count for r in self.collections)

    @property
    def total_inserted(self) -> int:
        return sum(r.inserted for r in self.collections)

    @property
    def total_skipped(self) -> int:
        return sum(1 for r in self.collections if r.status == "SKIPPED")

    @property
    def total_failed(self) -> int:
        return sum(1 for r in self.collections if r.status == "FAILED")

    @property
    def overall_status(self) -> str:
        if self.total_failed > 0:
            return "FAIL"
        return "PASS"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_old_databases(vectors_root: Path) -> List[Path]:
    """
    Return a sorted list of subdirectories inside *vectors_root* that
    contain a ``chroma.sqlite3`` file.

    The root directory itself is excluded (it is the migration target).
    Hidden directories (name starts with ``.``) are excluded.
    Non-directory entries are excluded.

    Args:
        vectors_root: Absolute path to ``data/vectors/``.

    Returns:
        List of ``Path`` objects, each pointing to an old per-collection
        database directory.
    """
    if not vectors_root.exists():
        logger.warning("vectors_root does not exist: %s", vectors_root)
        return []

    result: List[Path] = []
    for entry in sorted(vectors_root.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith("."):
            continue
        if (entry / "chroma.sqlite3").exists():
            result.append(entry)

    logger.info("Discovered %d old database(s) in %s", len(result), vectors_root)
    return result


# ---------------------------------------------------------------------------
# Core migration
# ---------------------------------------------------------------------------

def migrate_collection(
    old_dir: Path,
    collection_name: str,
    root_client: chromadb.PersistentClient,
    dry_run: bool,
) -> CollectionResult:
    """
    Migrate one collection from an old per-directory database into the
    shared root PersistentClient.

    Steps:
      1. Open the old database and read all vectors in batches.
      2. Open (or create) the target collection in the root client.
      3. Determine which IDs are already present (idempotency).
      4. Insert only the missing IDs.
      5. Verify the final count matches the old count.

    Args:
        old_dir:         Path to the subdirectory containing the old database.
        collection_name: Name of the collection to migrate.
        root_client:     Open PersistentClient at the shared root.
        dry_run:         When True, read but do not write anything.

    Returns:
        ``CollectionResult`` describing what happened.
    """
    logger.info("Migrating collection %r from %s", collection_name, old_dir.name)

    # ── Open old database ─────────────────────────────────────────────
    try:
        old_client = chromadb.PersistentClient(path=str(old_dir))
        old_col = old_client.get_collection(collection_name)
        old_count = old_col.count()
    except Exception as exc:
        logger.error("Cannot open old database at %s: %s", old_dir, exc)
        return CollectionResult(
            source_dir=str(old_dir),
            collection_name=collection_name,
            old_count=0,
            new_count_before=0,
            inserted=0,
            status="FAILED",
            error=str(exc),
        )

    logger.info("  Old collection: %d vectors", old_count)

    # ── Read all vectors from old collection ──────────────────────────
    try:
        all_data = old_col.get(
            include=["documents", "embeddings", "metadatas"],
            limit=old_count + 1,   # +1 as a safety margin
        )
    except Exception as exc:
        logger.error("Cannot read old collection %r: %s", collection_name, exc)
        return CollectionResult(
            source_dir=str(old_dir),
            collection_name=collection_name,
            old_count=old_count,
            new_count_before=0,
            inserted=0,
            status="FAILED",
            error=f"Read failed: {exc}",
        )

    all_ids: List[str] = all_data["ids"]
    all_docs = all_data.get("documents") or [""] * len(all_ids)
    all_embs = all_data.get("embeddings")
    all_metas = all_data.get("metadatas") or [{} for _ in all_ids]

    if all_embs is None:
        logger.error("No embeddings returned for collection %r", collection_name)
        return CollectionResult(
            source_dir=str(old_dir),
            collection_name=collection_name,
            old_count=old_count,
            new_count_before=0,
            inserted=0,
            status="FAILED",
            error="Embeddings were None",
        )

    # ── Open / create target collection in root ───────────────────────
    try:
        # Preserve the collection metadata (distance metric, model, schema)
        old_meta = old_col.metadata or {}
        target_col = root_client.get_or_create_collection(
            name=collection_name,
            metadata=old_meta,
        )
        new_count_before = target_col.count()
    except Exception as exc:
        logger.error("Cannot open/create target collection %r: %s", collection_name, exc)
        return CollectionResult(
            source_dir=str(old_dir),
            collection_name=collection_name,
            old_count=old_count,
            new_count_before=0,
            inserted=0,
            status="FAILED",
            error=f"Target collection error: {exc}",
        )

    # ── Idempotency: skip if already fully migrated ───────────────────
    if new_count_before >= old_count:
        logger.info(
            "  Collection %r already has %d vectors (>= %d) — SKIPPED",
            collection_name, new_count_before, old_count,
        )
        return CollectionResult(
            source_dir=str(old_dir),
            collection_name=collection_name,
            old_count=old_count,
            new_count_before=new_count_before,
            inserted=0,
            status="SKIPPED",
        )

    if dry_run:
        logger.info("  DRY RUN — would insert %d vectors", old_count - new_count_before)
        return CollectionResult(
            source_dir=str(old_dir),
            collection_name=collection_name,
            old_count=old_count,
            new_count_before=new_count_before,
            inserted=0,
            status="DRY_RUN",
        )

    # ── Determine which IDs are missing (partial idempotency) ─────────
    try:
        existing_in_target = set(target_col.get(include=[])["ids"])
    except Exception as exc:
        logger.error("Cannot list existing IDs in target: %s", exc)
        return CollectionResult(
            source_dir=str(old_dir),
            collection_name=collection_name,
            old_count=old_count,
            new_count_before=new_count_before,
            inserted=0,
            status="FAILED",
            error=f"ID list failed: {exc}",
        )

    # Build lists of only the vectors not yet in the target
    ids_to_insert    : List[str]   = []
    docs_to_insert   : List[str]   = []
    embs_to_insert   : list        = []
    metas_to_insert  : List[dict]  = []

    for i, vid in enumerate(all_ids):
        if vid not in existing_in_target:
            ids_to_insert.append(vid)
            docs_to_insert.append(all_docs[i] if all_docs[i] is not None else "")
            embs_to_insert.append(
                all_embs[i].tolist()
                if hasattr(all_embs[i], "tolist")
                else list(all_embs[i])
            )
            metas_to_insert.append(all_metas[i] if all_metas[i] is not None else {})

    if not ids_to_insert:
        logger.info("  All %d vectors already present — SKIPPED", old_count)
        return CollectionResult(
            source_dir=str(old_dir),
            collection_name=collection_name,
            old_count=old_count,
            new_count_before=new_count_before,
            inserted=0,
            status="SKIPPED",
        )

    logger.info("  Inserting %d vectors (skipping %d already present) ...",
                len(ids_to_insert), len(existing_in_target))

    # ── Batched insert ─────────────────────────────────────────────────
    total_inserted = 0
    n = len(ids_to_insert)
    total_batches = (n + _BATCH_SIZE - 1) // _BATCH_SIZE

    try:
        for b in range(total_batches):
            start = b * _BATCH_SIZE
            end   = min(start + _BATCH_SIZE, n)
            target_col.add(
                ids       = ids_to_insert[start:end],
                documents = docs_to_insert[start:end],
                embeddings= embs_to_insert[start:end],
                metadatas = metas_to_insert[start:end],
            )
            total_inserted += end - start
            logger.debug("    Batch %d/%d done (%d vectors)", b + 1, total_batches, end - start)
    except Exception as exc:
        logger.error("Insertion failed on batch %d: %s", b + 1, exc)
        return CollectionResult(
            source_dir=str(old_dir),
            collection_name=collection_name,
            old_count=old_count,
            new_count_before=new_count_before,
            inserted=total_inserted,
            status="FAILED",
            error=f"Insertion error: {exc}",
        )

    # ── Verify count ───────────────────────────────────────────────────
    final_count = target_col.count()
    if final_count < old_count:
        msg = (
            f"Count mismatch: old={old_count}  "
            f"target_final={final_count}  inserted={total_inserted}"
        )
        logger.error("VERIFICATION FAILED for %r: %s", collection_name, msg)
        return CollectionResult(
            source_dir=str(old_dir),
            collection_name=collection_name,
            old_count=old_count,
            new_count_before=new_count_before,
            inserted=total_inserted,
            status="FAILED",
            error=msg,
        )

    logger.info("  Verification passed: %d vectors in target", final_count)
    return CollectionResult(
        source_dir=str(old_dir),
        collection_name=collection_name,
        old_count=old_count,
        new_count_before=new_count_before,
        inserted=total_inserted,
        status="MIGRATED",
    )


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

def print_report(summary: MigrationSummary, dry_run: bool) -> None:
    """Print a formatted ASCII migration summary table."""
    w = _COL_WIDTH
    sep = "=" * (w + 30)
    mid = "-" * (w + 30)
    header_label = " DRY RUN REPORT" if dry_run else " MIGRATION REPORT"

    print()
    print(sep)
    print(f"  NEXORA VECTOR STORE{header_label}")
    print(sep)
    print(f"  {'Collection':<{w}} {'Old':>6}  {'New':>6}  {'Status'}")
    print(mid)

    for r in summary.collections:
        new_display = r.old_count if r.status in ("MIGRATED", "SKIPPED") else r.new_count_before + r.inserted
        print(f"  {r.collection_name:<{w}} {r.old_count:>6}  {new_display:>6}  {r.status}")
        if r.error:
            print(f"  {'':>{w}}  {'':>6}  {'':>6}  ERROR: {r.error}")

    print(mid)
    print(f"  {'TOTAL':<{w}} {summary.total_old:>6}  {summary.total_old:>6}  {summary.overall_status}")
    print(sep)
    print(f"  Collections discovered : {len(summary.collections)}")
    print(f"  Collections migrated   : {len([r for r in summary.collections if r.status == 'MIGRATED'])}")
    print(f"  Collections skipped    : {summary.total_skipped}")
    print(f"  Collections failed     : {summary.total_failed}")
    print(f"  Vectors copied         : {summary.total_inserted}")
    print(sep)
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Migrate historical Nexora vector databases into a single shared PersistentClient.",
    )
    parser.add_argument(
        "--vectors-root",
        default=str(_DEFAULT_VECTORS_ROOT),
        help=f"Path to the vectors root directory.  Default: {_DEFAULT_VECTORS_ROOT}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect old databases and report what would be migrated without writing anything.",
    )
    return parser.parse_args()


def main() -> int:
    """
    Entry point.

    Returns:
        0 on full success, 1 if any collection failed.
    """
    args = parse_args()
    vectors_root = Path(args.vectors_root).resolve()
    dry_run: bool = args.dry_run

    logger.info("vectors_root : %s", vectors_root)
    logger.info("dry_run      : %s", dry_run)

    # ── Discover old databases ────────────────────────────────────────
    old_dirs = discover_old_databases(vectors_root)
    if not old_dirs:
        logger.info("No old databases found.  Nothing to migrate.")
        return 0

    # ── Open shared root client (target) ─────────────────────────────
    if not dry_run:
        try:
            vectors_root.mkdir(parents=True, exist_ok=True)
            root_client = chromadb.PersistentClient(path=str(vectors_root))
            root_client.heartbeat()
            logger.info("Root PersistentClient opened at %s", vectors_root)
        except Exception as exc:
            logger.error("Cannot open root PersistentClient: %s", exc)
            return 1
    else:
        root_client = None  # type: ignore[assignment]  # not used in dry run

    # ── Migrate each database ─────────────────────────────────────────
    summary = MigrationSummary()

    for old_dir in old_dirs:
        try:
            old_client = chromadb.PersistentClient(path=str(old_dir))
            collections = old_client.list_collections()
        except Exception as exc:
            logger.error("Cannot inspect %s: %s", old_dir, exc)
            summary.collections.append(CollectionResult(
                source_dir=str(old_dir),
                collection_name="<unknown>",
                old_count=0,
                new_count_before=0,
                inserted=0,
                status="FAILED",
                error=str(exc),
            ))
            continue

        if not collections:
            logger.warning("Directory %s contains a database but no collections — skipping.", old_dir.name)
            continue

        for col_info in collections:
            result = migrate_collection(
                old_dir=old_dir,
                collection_name=col_info.name,
                root_client=root_client,  # type: ignore[arg-type]
                dry_run=dry_run,
            )
            summary.collections.append(result)

            # Hard stop on verification failure
            if result.status == "FAILED":
                logger.error(
                    "STOPPING: migration failed for %r — check errors above.",
                    col_info.name,
                )
                print_report(summary, dry_run)
                return 1

    # ── Final report ──────────────────────────────────────────────────
    print_report(summary, dry_run)

    return 0 if summary.overall_status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
