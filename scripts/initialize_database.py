from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from ffcu.config import Settings
from ffcu.database import Database
from ffcu.services.content_loader import load_content


def main() -> None:
    settings = Settings.from_env()
    database = Database(settings.database_url)
    database.create_all()
    with database.session() as session:
        summary = load_content(session, settings.content_directory, settings.default_passing_score)
    database.dispose()
    print(
        f"Database ready: {summary.levels} levels, {summary.lessons} lessons, "
        f"{summary.questions} questions, {summary.assignments} assignments."
    )


if __name__ == "__main__":
    main()
