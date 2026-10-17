from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from ffcu.config import Settings
from ffcu.database import Database
from ffcu.services.backup import backup_sqlite


def main() -> None:
    settings = Settings.from_env()
    database = Database(settings.database_url)
    source = database.sqlite_path
    database.dispose()
    if source is None:
        raise SystemExit("The helper supports SQLite only. Use your PostgreSQL provider's backup tool after migration.")
    destination = backup_sqlite(source, settings.backup_directory)
    print(f"Backup created: {destination}")


if __name__ == "__main__":
    main()
