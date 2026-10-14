"""Test setup: in-memory SQLite, hashing embedder, mock LLM. No Docker, API key or internet required."""

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="snapfix-tests-")
os.environ.update({
    "DATABASE_URL": "sqlite+pysqlite:///:memory:",
    "EMBEDDING_BACKEND": "hash",
    "LLM_MODE": "mock",
    "ANTHROPIC_API_KEY": "",
    "SCHEDULER_ENABLED": "false",
    "NOTIFIER": "console",
    "ADMIN_TOKEN": "test-token",
    "STT_FALLBACK": "none",
    "UPLOAD_DIR": os.path.join(_TMP, "uploads"),
    "EVAL_RESULTS_DIR": os.path.join(_TMP, "eval"),
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal, init_engine  # noqa: E402
from app.models import Base  # noqa: E402
from app.seed import generate  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    eng = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


def _seed() -> dict:
    db = SessionLocal()
    try:
        return generate.run(db)
    finally:
        db.close()


@pytest.fixture(scope="session")
def seeded(engine) -> dict:
    return _seed()


@pytest.fixture
def reseed(engine) -> dict:
    """Fresh demo state for tests that mutate data."""
    return _seed()


@pytest.fixture
def db(engine):
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(seeded):
    from app.main import app

    with TestClient(app) as c:
        yield c
