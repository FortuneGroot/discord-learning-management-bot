from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from ffcu.database import Database
from ffcu.services.content_loader import load_content


def main() -> None:
    database = Database("sqlite:///:memory:")
    database.create_all()
    with database.session() as session:
        summary = load_content(session, PROJECT / "content")
    print(f"Content valid: {summary.levels} levels, {summary.lessons} lessons, {summary.questions} questions.")


if __name__ == "__main__":
    main()
