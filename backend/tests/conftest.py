"""Minimal pytest harness (Phase 1). Phase 4 expands this into the full pyramid
(unit/integration/flow markers, ephemeral tmpfs Postgres, external mocks).

Requires TEST_DATABASE_URL pointing at an ephemeral test database whose name
contains "test" — a guard refuses to run the destructive cleanup otherwise.
"""

from __future__ import annotations

import os

import pytest

_TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
if _TEST_DB_URL:
    # Must be set before importing app.* so the engine binds to the test DB.
    os.environ["DATABASE_URL"] = _TEST_DB_URL


def _is_test_db(url: str) -> bool:
    return "test" in (url.rsplit("/", 1)[-1].lower())


@pytest.fixture(scope="session", autouse=True)
def _require_test_db():
    url = os.environ.get("DATABASE_URL", "")
    if not url or not _is_test_db(url):
        pytest.skip("TEST_DATABASE_URL must point at a *_test database")
    _ensure_prisma_session_table()
    yield


def _ensure_prisma_session_table() -> None:
    """The Shopify OAuth ``Session`` table is owned by Prisma (Node side), not
    Alembic — but backend token-refresh write-back reads/writes it, and at runtime
    both tables live in the same Postgres. Alembic-only test DBs lack it, so
    create it here from the shipped idempotent DDL to mirror runtime."""
    from pathlib import Path

    from sqlalchemy import text

    from app.db.session import SessionLocal

    ddl_path = Path(__file__).resolve().parents[2] / "shopify" / "prisma" / "ensure-session-table.sql"
    ddl = ddl_path.read_text(encoding="utf-8")
    session = SessionLocal()
    try:
        session.execute(text(ddl))
        session.commit()
    finally:
        session.close()


@pytest.fixture()
def db():
    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_tables():
    """Reset mutable tables between tests. Guarded to the ephemeral test DB."""
    from sqlalchemy import text

    from app.db.session import SessionLocal, engine

    if not _is_test_db(str(engine.url)):
        pytest.fail("Refusing destructive cleanup against a non-test database")
    session = SessionLocal()
    try:
        for tbl in (
            "async_jobs", "webhook_events", "server_events", "pending_purchases", "market_pixels", "markets", "app_keys",
            "billing_subscription_events", "usage_counters",
            "tenant_subscriptions", "tenants_metadata", "tenants", '"Session"',
        ):
            session.execute(text(f"DELETE FROM {tbl}"))
        session.commit()
    finally:
        session.close()
    yield


INTERNAL_HEADERS = {"X-Internal-Key": "dev-internal-key"}
