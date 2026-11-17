"""Test fixtures.

Strategy:
- Tests run against a real PostgreSQL database (`tie_test`), not SQLite, because we rely on
  Postgres-specific features (CITEXT, JSONB, ENUM, ON CONFLICT, CHECK constraints).
- Once per session, the schema is built by running the real Alembic migrations
  (downgrade to base, then upgrade to head), so the migrations themselves are tested on every run.
- Each test runs inside an outer transaction that is rolled back afterwards. The Session uses
  join_transaction_mode="create_savepoint", so a service calling session.commit() only
  releases a SAVEPOINT, and nothing a test writes survives the test.
"""

import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get(
        "TEST_DATABASE_URL", "postgresql+psycopg://tie:tie_dev_password@localhost:5433/tie_test"
    ),
)

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = get_settings().database_url
    assert "test" in url, f"Refusing to run tests against a non-test database: {url}"
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["database_url"] = url
    cfg.attributes["configure_logger"] = False
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    eng = create_engine(url)
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    connection = engine.connect()
    outer = connection.begin()
    session = Session(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def register_and_login(
    client: TestClient, email: str = "alice@example.com", password: str = "correct-horse-battery"
) -> dict[str, Any]:
    r = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    tokens: dict[str, Any] = r.json()
    return tokens


def auth_header(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}
