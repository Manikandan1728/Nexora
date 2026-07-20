#!/usr/bin/env python3
"""
scripts/migrate_telegram_session.py

[ADDITIVE] Part 2C — Phase 6: Database migration script for Telegram Sessions.
Adds the new encrypted session bundle columns and status/timestamps to tg_accounts.

Run this script directly from the project root:
  python scripts/migrate_telegram_session.py
"""

import sqlite3
import sys
from pathlib import Path

# Resolve path to the SQLite DB
DB_PATH = Path(__file__).resolve().parents[1] / "data" / "storage" / "nexora_telegram.db"

def migrate():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}. No migration needed.")
        return

    print(f"Migrating database at {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    columns_to_add = [
        ("session_status", "VARCHAR(32) NOT NULL DEFAULT 'absent'"),
        ("tdlib_database_key_encrypted", "TEXT NULL"),
        ("tdlib_files_database_key_encrypted", "TEXT NULL"),
        ("session_locator_encrypted", "TEXT NULL"),
        ("session_created_at", "DATETIME NULL"),
        ("session_updated_at", "DATETIME NULL"),
        ("session_last_restored_at", "DATETIME NULL"),
    ]

    try:
        # Check existing columns to avoid duplicate column errors
        cursor.execute("PRAGMA table_info(tg_accounts);")
        existing_cols = {row[1] for row in cursor.fetchall()}

        for col_name, col_type in columns_to_add:
            if col_name not in existing_cols:
                print(f"Adding column {col_name} to tg_accounts...")
                cursor.execute(f"ALTER TABLE tg_accounts ADD COLUMN {col_name} {col_type};")
            else:
                print(f"Column {col_name} already exists.")

        conn.commit()
        print("Migration complete!")
    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
