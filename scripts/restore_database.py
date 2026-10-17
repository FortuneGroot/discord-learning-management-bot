from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from ffcu.config import Settings
from ffcu.database import Database
from ffcu.services.backup import restore_sqlite


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore an FFCU SQLite backup while the bot is stopped.")
    parser.add_argument("backup", type=Path)
    parser.add_argument("--yes", action="store_true", help="Confirm replacement of the configured database")
    args = parser.parse_args()
    if not args.yes:
        raise SystemExit("Restore cancelled. Re-run with --yes after stopping the bot and confirming the backup path.")
    settings = Settings.from_env()
    database = Database(settings.database_url)
    destination = database.sqlite_path
    database.dispose()
    if destination is None:
        raise SystemExit("The helper supports SQLite only.")
    restore_sqlite(args.backup, destination)
    print(f"Database restored from {args.backup.resolve()}")


if __name__ == "__main__":
    main()
