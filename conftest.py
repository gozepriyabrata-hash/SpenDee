import sys

import pytest

import database.db as db


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Isolated DB for pure database/db.py unit tests — no Flask involved."""
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "unit.db"))
    db.init_db()
    return db


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Isolated DB + fresh app import for route tests.

    app.py runs init_db()/seed_db() at import time, so DB_PATH must be
    patched before `import app` executes, and app.py must be re-imported
    fresh per test so its top-level code reruns against the patched path.
    """
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app_test.db"))
    sys.modules.pop("app", None)
    import app as app_module

    app_module.app.config.update(TESTING=True)
    yield app_module.app
    sys.modules.pop("app", None)
