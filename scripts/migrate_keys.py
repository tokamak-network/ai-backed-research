#!/usr/bin/env python3
"""Migrate existing keys.json to SQLite database.

Usage:
    python scripts/migrate_keys.py

This script:
1. Reads keys from keys.json
2. Initializes the SQLite database
3. Inserts each key as a legacy key (no researcher association)
4. Renames keys.json to keys.json.backup
"""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from research_cli.db import init_db, create_legacy_key, get_connection

KEYS_FILE = Path("keys.json")
BACKUP_FILE = Path("keys.json.backup")


def main():
    # Initialize database
    print("Initializing SQLite database...")
    init_db()

    # Read keys.json
    if not KEYS_FILE.exists():
        print("No keys.json found. Nothing to migrate.")
        return

    try:
        with open(KEYS_FILE) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error reading keys.json: {e}")
        return

    keys = data.get("keys", [])
    if not keys:
        print("No keys found in keys.json. Nothing to migrate.")
        return

    # Migrate each key
    migrated = 0
    for entry in keys:
        key_value = entry.get("key", "")
        label = entry.get("label", "")
        if not key_value:
            continue

        print(f"  Migrating key: {key_value[:8]}... (label: {label or '-'})")
        create_legacy_key(key_value, label=f"legacy: {label}" if label else "legacy key")
        migrated += 1

    print(f"\nMigrated {migrated} key(s) to SQLite.")

    # Verify
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) as c FROM api_keys").fetchone()["c"]
    print(f"Total keys in database: {count}")

    # Backup original file
    if KEYS_FILE.exists():
        KEYS_FILE.rename(BACKUP_FILE)
        print(f"\nRenamed keys.json -> keys.json.backup")

    print("Migration complete.")


if __name__ == "__main__":
    main()
