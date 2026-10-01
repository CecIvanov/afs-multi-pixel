"""Offline-token auto-refresh: the mechanism that keeps a tenant's Shopify access
token alive so background workers never hit a dead token.

Covers the value object + error classifier (pure), the proactive discovery sweep,
the OAuth exchange (happy path + dead-token revocation + not-due no-op), the
Session-table write-back (rotating refresh tokens must stay in lockstep), the
durable job handler, session backfill, and the reactive 401-recovery in the queue.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

SHOP = "refresh-shop.myshopify.com"


# --- fakes ------------------------------------------------------------------
class _FakeResp:
    def __init__(self, status_code: int, payload: dict | None = None, text_body: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text_body

    def json(self):
        return self._payload


def _ok_token_payload(**overrides) -> dict:
    payload = {
        "access_token": "shpat_new",
        "expires_in": 86400,
        "refresh_token": "shprt_new",
        "refresh_token_expires_in": 86400 * 30,
        "scope": "write_products",
    }
    payload.update(overrides)
    return payload


def _set_backend_shopify_creds(monkeypatch) -> None:
    from app.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "shopify_api_key", "test-key")
    monkeypatch.setattr(s, "shopify_api_secret", "test-secret")


def _make_tenant(db, *, refresh_token="shprt_1", access_expires=None, refresh_expires=None):
    from app.services.tenant_service import TenantService

    return TenantService(db).create_tenant(
        SHOP,
        access_token="shpat_1",
        scopes="write_products",
        refresh_token=refresh_token,
        access_token_expires_at=access_expires,
        refresh_token_expires_at=refresh_expires,
    )


def _insert_offline_session(db, *, access_token="shpat_1", refresh_token="shprt_1") -> None:
    db.execute(
        text(
            'INSERT INTO "Session" (id, shop, state, "isOnline", "accessToken", "refreshToken") '
            "VALUES (:id, :shop, '', false, :at, :rt)"
        ),
        {"id": f"offline_{SHOP}", "shop": SHOP, "at": access_token, "rt": refresh_token},
    )
    db.commit()


# --- pure logic -------------------------------------------------------------
@pytest.mark.unit
def test_credentials_from_oauth_response_computes_expiries():
    from app.services.shopify_token_credentials import ShopifyTokenCredentials

    now = datetime(2026, 1, 1, tzinfo=UTC)
    creds = ShopifyTokenCredentials.from_oauth_refresh_response(_ok_token_payload(), now=now)
    assert creds.access_token == "shpat_new"
    assert creds.refresh_token == "shprt_new"
    assert creds.access_token_expires_at == now + timedelta(seconds=86400)
    assert creds.refresh_token_expires_at == now + timedelta(seconds=86400 * 30)
    assert creds.scopes == "write_products"


@pytest.mark.unit
def test_credentials_non_expiring_leaves_expiries_null():
    from app.services.shopify_token_credentials import ShopifyTokenCredentials

    creds = ShopifyTokenCredentials.from_oauth_refresh_response({"access_token": "shpat_x"})
    assert creds.access_token_expires_at is None
    assert creds.refresh_token_expires_at is None
    assert creds.refresh_token is None


@pytest.mark.unit
def test_dead_refresh_token_classification():
    from app.services.shopify_oauth_refresh_errors import (
        is_definitive_dead_refresh_token_error,
        parse_oauth_token_error,
    )

    invalid_grant = parse_oauth_token_error('{"error":"invalid_grant","error_description":"refresh_token is invalid"}')
    assert is_definitive_dead_refresh_token_error(invalid_grant) is True

    active_req = parse_oauth_token_error(
        '{"error":"invalid_request","error_description":"There is already an active refresh_token"}'
    )
    assert is_definitive_dead_refresh_token_error(active_req) is True

    transient = parse_oauth_token_error('{"error":"server_error","error_description":"temporary"}')
    assert is_definitive_dead_refresh_token_error(transient) is False

    assert is_definitive_dead_refresh_token_error(parse_oauth_token_error("not json")) is False
    assert is_definitive_dead_refresh_token_error(None) is False


@pytest.mark.unit
def test_shopify_auth_error_detection():
    from app.services.shopify_oauth_refresh_errors import is_shopify_auth_error

    assert is_shopify_auth_error("Shopify API HTTP 401: unauthorized") is True
    assert is_shopify_auth_error("Invalid API key or access token") is True
    assert is_shopify_auth_error("connection reset by peer") is False
    assert is_shopify_auth_error("Shopify API HTTP 500: boom") is False


# --- discovery sweep --------------------------------------------------------
@pytest.mark.integration
def test_discover_enqueues_due_tenant_once(db):
    from app.models import AsyncJob, AsyncJobOperation, AsyncJobStatus
    from app.services.shopify_token_refresh_service import ShopifyTokenRefreshService
    from sqlalchemy import select

    _make_tenant(db, access_expires=datetime.now(UTC) - timedelta(hours=1))

    result = ShopifyTokenRefreshService(db).discover_and_enqueue_refreshes()
    assert result == {"candidates": 1, "enqueued": 1}

    jobs = db.scalars(
        select(AsyncJob).where(
            AsyncJob.operation == AsyncJobOperation.TOKEN_REFRESH,
            AsyncJob.status == AsyncJobStatus.PENDING,
        )
    ).all()
    assert len(jobs) == 1

    # A pending token_refresh already exists -> the second sweep is a no-op.
    assert ShopifyTokenRefreshService(db).discover_and_enqueue_refreshes()["enqueued"] == 0


@pytest.mark.integration
def test_discover_skips_not_due_and_revoked(db):
    from app.models import Tenant
    from app.services.shopify_token_refresh_service import ShopifyTokenRefreshService

    # Far-future expiry -> not due.
    t = _make_tenant(db, access_expires=datetime.now(UTC) + timedelta(days=5))
    assert ShopifyTokenRefreshService(db).discover_and_enqueue_refreshes()["enqueued"] == 0

    # Due, but the refresh chain is revoked -> excluded.
    t = db.get(Tenant, t.id)
    t.access_token_expires_at = datetime.now(UTC) - timedelta(hours=1)
    t.shopify_refresh_token_revoked_at = datetime.now(UTC)
    db.commit()
    assert ShopifyTokenRefreshService(db).discover_and_enqueue_refreshes()["enqueued"] == 0


# --- the exchange -----------------------------------------------------------
@pytest.mark.flow
def test_refresh_happy_path_updates_tenant_and_session(db, monkeypatch):
    from app.models import Tenant
    from app.services.shopify_token_refresh_service import ShopifyTokenRefreshService

    _set_backend_shopify_creds(monkeypatch)
    tenant = _make_tenant(db, access_expires=datetime.now(UTC) - timedelta(hours=1))
    _insert_offline_session(db)

    monkeypatch.setattr(
        "app.services.shopify_token_refresh_service.httpx.post",
        lambda *a, **k: _FakeResp(200, _ok_token_payload()),
    )

    refreshed = ShopifyTokenRefreshService(db).refresh_tenant_tokens(tenant, reason="test")
    assert refreshed is True

    t = db.get(Tenant, tenant.id)
    assert t.access_token == "shpat_new"
    assert t.refresh_token == "shprt_new"
    assert t.access_token_expires_at > datetime.now(UTC)
    assert t.shopify_refresh_token_revoked_at is None

    # The rotating token was mirrored into the Prisma Session row (critical — the
    # old refresh token is now dead on Shopify's side).
    row = db.execute(
        text('SELECT "accessToken", "refreshToken" FROM "Session" WHERE shop = :s'), {"s": SHOP}
    ).first()
    assert row[0] == "shpat_new" and row[1] == "shprt_new"


@pytest.mark.flow
def test_refresh_dead_token_marks_revoked(db, monkeypatch):
    from app.models import Tenant
    from app.services.shopify_token_refresh_service import (
        ShopifyRefreshTokenRevokedError,
        ShopifyTokenRefreshService,
    )

    _set_backend_shopify_creds(monkeypatch)
    tenant = _make_tenant(db, access_expires=datetime.now(UTC) - timedelta(hours=1))

    monkeypatch.setattr(
        "app.services.shopify_token_refresh_service.httpx.post",
        lambda *a, **k: _FakeResp(
            400, text_body='{"error":"invalid_grant","error_description":"refresh_token is invalid"}'
        ),
    )

    with pytest.raises(ShopifyRefreshTokenRevokedError):
        ShopifyTokenRefreshService(db).refresh_tenant_tokens(tenant, reason="test")

    t = db.get(Tenant, tenant.id)
    assert t.shopify_refresh_token_revoked_at is not None


@pytest.mark.flow
def test_refresh_not_due_is_noop(db, monkeypatch):
    from app.services.shopify_token_refresh_service import ShopifyTokenRefreshService

    _set_backend_shopify_creds(monkeypatch)
    tenant = _make_tenant(
        db,
        access_expires=datetime.now(UTC) + timedelta(days=1),
        refresh_expires=datetime.now(UTC) + timedelta(days=30),
    )

    called = {"n": 0}

    def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("should not exchange when not due")

    monkeypatch.setattr("app.services.shopify_token_refresh_service.httpx.post", _boom)
    assert ShopifyTokenRefreshService(db).refresh_tenant_tokens(tenant, reason="test") is False
    assert called["n"] == 0


@pytest.mark.flow
def test_backfill_refresh_token_from_session(db, monkeypatch):
    """A tenant installed before this feature has no refresh_token column value;
    the service self-heals it from the Prisma Session row, then exchanges."""
    from app.models import Tenant
    from app.services.shopify_token_refresh_service import ShopifyTokenRefreshService

    _set_backend_shopify_creds(monkeypatch)
    tenant = _make_tenant(db, refresh_token=None, access_expires=datetime.now(UTC) - timedelta(hours=1))
    _insert_offline_session(db, refresh_token="shprt_from_session")

    monkeypatch.setattr(
        "app.services.shopify_token_refresh_service.httpx.post",
        lambda *a, **k: _FakeResp(200, _ok_token_payload()),
    )
    assert ShopifyTokenRefreshService(db).refresh_tenant_tokens(tenant, reason="test") is True
    assert db.get(Tenant, tenant.id).refresh_token == "shprt_new"


# --- durable job handler ----------------------------------------------------
@pytest.mark.flow
def test_token_refresh_job_handler_refreshes(db, monkeypatch):
    from app.models import Tenant
    from app.services.async_job_service import AsyncJobService
    from app.services.job_processors import dispatch_job

    _set_backend_shopify_creds(monkeypatch)
    tenant = _make_tenant(db, access_expires=datetime.now(UTC) - timedelta(hours=1))
    monkeypatch.setattr(
        "app.services.shopify_token_refresh_service.httpx.post",
        lambda *a, **k: _FakeResp(200, _ok_token_payload()),
    )

    job = AsyncJobService(db).enqueue_token_refresh(tenant.id)
    dispatch_job(db, job)
    assert db.get(Tenant, tenant.id).access_token == "shpat_new"


# --- reactive 401-recovery in the queue -------------------------------------
@pytest.mark.integration
def test_401_recovery_refreshes_then_retries(db, monkeypatch):
    from app.models import AsyncJob, AsyncJobStatus
    from app.services.async_job_service import AsyncJobService

    tenant = _make_tenant(db)
    svc = AsyncJobService(db)
    job = svc.enqueue_shop_info_fetch(tenant.id)

    calls = {"dispatch": 0, "refresh": 0}

    def _fake_dispatch(_db, _job):
        calls["dispatch"] += 1
        if calls["dispatch"] == 1:
            raise RuntimeError("Shopify API HTTP 401: token expired")
        return None  # succeeds on the retry with the fresh token

    def _fake_refresh(self, tenant, *, reason, force=False):
        calls["refresh"] += 1
        return True

    monkeypatch.setattr("app.services.job_processors.dispatch_job", _fake_dispatch)
    monkeypatch.setattr(
        "app.services.shopify_token_refresh_service.ShopifyTokenRefreshService.refresh_tenant_tokens",
        _fake_refresh,
    )

    svc.process_job(job.id)

    assert calls == {"dispatch": 2, "refresh": 1}
    assert db.get(AsyncJob, job.id).status == AsyncJobStatus.COMPLETED


@pytest.mark.integration
def test_revoked_tenant_admin_job_completes_without_dispatch(db, monkeypatch):
    """A dead refresh chain must NOT cause 5 doomed 401 Admin calls + a FAILED job.
    The pre-dispatch guard short-circuits non-allowlisted ops straight to COMPLETED."""
    from app.models import AsyncJob, AsyncJobStatus, Tenant
    from app.services.async_job_service import AsyncJobService

    tenant = _make_tenant(db)
    db.get(Tenant, tenant.id).shopify_refresh_token_revoked_at = datetime.now(UTC)
    db.commit()

    def _must_not_dispatch(_db, _job):
        raise AssertionError("revoked tenant's Admin-API job must not be dispatched")

    monkeypatch.setattr("app.services.job_processors.dispatch_job", _must_not_dispatch)

    svc = AsyncJobService(db)
    job = svc.enqueue_shop_info_fetch(tenant.id)  # not in the revoked allowlist
    svc.process_job(job.id)

    assert db.get(AsyncJob, job.id).status == AsyncJobStatus.COMPLETED


@pytest.mark.integration
def test_revoked_tenant_allowlisted_op_still_runs(db, monkeypatch):
    """Lifecycle/local ops (e.g. scopes_update, uninstall) must still dispatch while
    revoked so the app winds down and re-auth can clear the flag."""
    from app.models import AsyncJob, AsyncJobOperation, AsyncJobStatus, Tenant
    from app.services.async_job_service import AsyncJobService

    tenant = _make_tenant(db)
    db.get(Tenant, tenant.id).shopify_refresh_token_revoked_at = datetime.now(UTC)
    db.commit()

    dispatched = {"n": 0}

    def _dispatch(_db, _job):
        dispatched["n"] += 1

    monkeypatch.setattr("app.services.job_processors.dispatch_job", _dispatch)

    svc = AsyncJobService(db)
    job = svc.enqueue(
        tenant_id=tenant.id, operation=AsyncJobOperation.SCOPES_UPDATE, topic="webhooks/scopes_update"
    )
    svc.process_job(job.id)

    assert dispatched["n"] == 1
    assert db.get(AsyncJob, job.id).status == AsyncJobStatus.COMPLETED


@pytest.mark.integration
def test_job_completes_when_refresh_chain_dies_mid_recovery(db, monkeypatch):
    """A job whose 401-recovery discovers a definitively dead token COMPLETES
    (revoked flag now set) instead of dead-lettering after five doomed attempts."""
    from app.models import AsyncJob, AsyncJobStatus
    from app.services.async_job_service import AsyncJobService
    from app.services.shopify_token_refresh_service import ShopifyRefreshTokenRevokedError

    tenant = _make_tenant(db)
    svc = AsyncJobService(db)
    job = svc.enqueue_shop_info_fetch(tenant.id)

    calls = {"dispatch": 0}

    def _dispatch_401(_db, _job):
        calls["dispatch"] += 1
        raise RuntimeError("Shopify API HTTP 401: token expired")

    def _refresh_dead(self, tenant, *, reason, force=False):
        raise ShopifyRefreshTokenRevokedError("dead on Shopify's side")

    monkeypatch.setattr("app.services.job_processors.dispatch_job", _dispatch_401)
    monkeypatch.setattr(
        "app.services.shopify_token_refresh_service.ShopifyTokenRefreshService.refresh_tenant_tokens",
        _refresh_dead,
    )

    svc.process_job(job.id)

    assert calls["dispatch"] == 1  # the single initial 401, then no retry storm
    assert db.get(AsyncJob, job.id).status == AsyncJobStatus.COMPLETED


@pytest.mark.integration
def test_401_recovery_not_applied_to_token_refresh_job(db, monkeypatch):
    """A failing token_refresh job must NOT trigger another refresh (infinite loop)."""
    from app.models import AsyncJob, AsyncJobStatus
    from app.services.async_job_service import AsyncJobService

    tenant = _make_tenant(db)
    svc = AsyncJobService(db)
    job = svc.enqueue_token_refresh(tenant.id)

    calls = {"refresh": 0}

    def _always_401(_db, _job):
        raise RuntimeError("Shopify API HTTP 401")

    def _count_refresh(self, tenant, *, reason, force=False):
        calls["refresh"] += 1
        return True

    monkeypatch.setattr("app.services.job_processors.dispatch_job", _always_401)
    monkeypatch.setattr(
        "app.services.shopify_token_refresh_service.ShopifyTokenRefreshService.refresh_tenant_tokens",
        _count_refresh,
    )

    svc.process_job(job.id)

    assert calls["refresh"] == 0  # recovery skipped for the token_refresh op itself
    # Retried (max_attempts not yet hit) rather than recovered.
    assert db.get(AsyncJob, job.id).status in (AsyncJobStatus.PENDING, AsyncJobStatus.FAILED)
