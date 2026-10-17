from __future__ import annotations

from pathlib import Path

import pytest

from ffcu.database import Database
from ffcu.services.content_loader import load_content


PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def database():
    db = Database("sqlite:///:memory:")
    db.create_all()
    with db.session() as session:
        load_content(session, PROJECT / "content")
    yield db
    db.dispose()
