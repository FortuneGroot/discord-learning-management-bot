from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def backup_sqlite(source: Path, backup_directory: Path) -> Path:
    source = source.resolve()
    if not source.exists():
        raise FileNotFoundError(f"Database not found: {source}")
    backup_directory = backup_directory.resolve()
    backup_directory.mkdir(parents=True, exist_ok=True)
    destination = backup_directory / f"ffcu-backup-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.db"
    with sqlite3.connect(source) as source_connection, sqlite3.connect(destination) as destination_connection:
        source_connection.backup(destination_connection)
    return destination


def restore_sqlite(backup: Path, destination: Path) -> None:
    backup, destination = backup.resolve(), destination.resolve()
    if not backup.exists() or backup.suffix.lower() != ".db":
        raise FileNotFoundError("Select an existing .db backup file.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(backup) as source_connection, sqlite3.connect(destination) as destination_connection:
        source_connection.backup(destination_connection)
