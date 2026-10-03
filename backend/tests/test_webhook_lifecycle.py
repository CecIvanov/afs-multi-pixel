"""Webhook lifecycle edge cases found comparing with BG Delivery: a stale uninstall
after a quick reinstall, GDPR jobs surviving an uninstall, the plan reset on
uninstall, personal data of skipped orders, scopes kept in step, coalescing, the
claim heartbeat and app_subscriptions/update."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.models import (
    AsyncJob,
    BillingReconcileSource,
    AsyncJobOperation,
    AsyncJobStatus,
    Tenant,
    TenantStatus,
    WebhookEvent,
    WebhookEventStatus,
)
from app.services.async_job_service import AsyncJobService
from app.services.billing_reconcile_service import BillingReconcileService
from app.services.billing_service import BillingService
from app.services.partner_billing_client import PartnerSubscriptionSnapshot
from app.services.tenant_service import TenantService
from app.services.webhook_ingest_service import WebhookIngestService
from tests.conftest import INTERNAL_HEADERS

SHOP = "lifecycle-shop.myshopify.com"


def _tenant(db) -> Tenant:
    return TenantService(db).sync_shopify_install(SHOP, access_token="shpat_x", scopes="read_markets")


def _ingest(db, topic, webhook_id, payload=None, triggered_at=None):
    return WebhookIngestService(db).ingest(
        shop_domain=SHOP, topic=topic, shopify_webhook_id=webhook_id, payload=payload, triggered_at=triggered_at
    )


def _run(db, job_id):
    job = db.get(AsyncJob, job_id)
    job.status = AsyncJobStatus.PROCESSING
    job.claimed_at = datetime.now(UTC)
    db.commit()
    AsyncJobService(db).process_job(job_id)
    db.expire_all()


def _session_row(db, scope="read_markets"):
    db.execute(
        text(
            'INSERT INTO "Session" (id, shop, state, "isOnline", scope, "accessToken") '
            "VALUES (:id, :shop, 's', false, :scope, 'shpat_new')"
        ),
        {"id": f"offline_{SHOP}", "shop": SHOP, "scope": scope},
    )
    db.commit()


# --- a stale app/uninstalled after a quick reinstall ---------------------------------
@pytest.mark.integration
def test_an_uninstall_fired_before_the_latest_app_open_is_skipped(db):
    tenant = _tenant(db)
    _session_row(db)
    fired = datetime.now(UTC) - timedelta(minutes=5)
    tenant.last_authenticated_at = datetime.now(UTC)  # reinstalled / reopened since
    db.commit()

    r = _ingest(db, "app/uninstalled", "u1", payload={"id": 1}, triggered_at=fired)
    _run(db, r.job_id)

    t = db.get(Tenant, tenant.id)
    assert t.status == TenantStatus.ACTIVE and t.access_token == "shpat_x"
    assert db.execute(text('SELECT count(*) FROM "Session" WHERE shop = :s'), {"s": SHOP}).scalar() == 1


@pytest.mark.integration
def test_an_uninstall_fired_after_the_latest_app_open_uninstalls(db):
    tenant = _tenant(db)
    tenant.last_authenticated_at = datetime.now(UTC) - timedelta(minutes=5)
    db.commit()

    r = _ingest(db, "app/uninstalled", "u2", payload={"id": 1}, triggered_at=datetime.now(UTC))
    _run(db, r.job_id)

    assert db.get(Tenant, tenant.id).status == TenantStatus.UNINSTALLED


@pytest.mark.integration
def test_app_open_marks_the_tenant_authenticated(client, db):
    body = {"shop_domain": SHOP, "access_token": "shpat_1", "scopes": "read_markets"}
    client.post("/api/v1/internal/shopify/install", json=body, headers=INTERNAL_HEADERS)
    first = db.scalar(select(Tenant.last_authenticated_at).where(Tenant.shop_domain == SHOP))
    client.post("/api/v1/internal/shopify/session-sync", json=body, headers=INTERNAL_HEADERS)
    db.expire_all()
    second = db.scalar(select(Tenant.last_authenticated_at).where(Tenant.shop_domain == SHOP))
    assert first is not None and second is not None and second >= first


# --- GDPR jobs survive the uninstall purge ---------------------------------------------
@pytest.mark.integration
def test_the_uninstall_keeps_pending_gdpr_jobs(db):
    tenant = _tenant(db)
    _ingest(db, "customers/data_request", "g1", payload={"customer": {"id": 7}})
    _ingest(db, "markets/update", "m1", payload={"id": 1})

    AsyncJobService(db).purge_tenant_active_jobs(tenant.id)

    ops = set(db.scalars(select(AsyncJob.operation).where(AsyncJob.tenant_id == tenant.id)).all())
    assert AsyncJobOperation.CUSTOMER_DATA_REQUEST in ops
    assert AsyncJobOperation.MARKETS_SYNC not in ops


# --- the plan resets on uninstall --------------------------------------------------------
@pytest.mark.integration
def test_an_uninstall_resets_the_plan_so_a_reinstall_has_none(db):
    tenant = _tenant(db)
    BillingReconcileService(db).reconcile(
        SHOP,
        PartnerSubscriptionSnapshot(has_active_contract=True, effective_plan_handle="light"),
        BillingReconcileSource.APP_LOAD,
    )
    assert BillingService(db).current_plan_handle(tenant.id) == "light"

    r = _ingest(db, "app/uninstalled", "u3", payload={"id": 1}, triggered_at=datetime.now(UTC) + timedelta(seconds=1))
    _run(db, r.job_id)
    TenantService(db).sync_shopify_install(SHOP, access_token="shpat_again")

    assert BillingService(db).current_plan_handle(tenant.id) == "none"
    assert db.get(Tenant, tenant.id).subscription_active is False


# --- personal data of orders nobody processes --------------------------------------------
@pytest.mark.integration
def test_an_order_from_an_unknown_shop_is_stored_without_its_body(db):
    WebhookIngestService(db).ingest(
        shop_domain="ghost.myshopify.com", topic="orders/create", shopify_webhook_id="o1",
        payload={"id": 1, "email": "a@b.c"},
    )
    event = db.scalars(select(WebhookEvent).where(WebhookEvent.shopify_webhook_id == "o1")).one()
    assert event.payload == {}


@pytest.mark.integration
def test_a_skipped_order_of_an_uninstalled_shop_drops_its_body(db):
    _tenant(db)
    r = _ingest(db, "orders/create", "o2", payload={"id": 2, "email": "a@b.c"})
    TenantService(db).sync_shopify_uninstall(SHOP)

    _run(db, r.job_id)

    assert db.get(AsyncJob, r.job_id) is None or db.get(AsyncJob, r.job_id).payload is None
    event = db.scalars(select(WebhookEvent).where(WebhookEvent.shopify_webhook_id == "o2")).one()
    assert event.payload == {}


# --- scopes ---------------------------------------------------------------------------------
@pytest.mark.integration
def test_scopes_update_also_updates_the_prisma_session(db):
    _tenant(db)
    _session_row(db, scope="read_markets")
    r = _ingest(db, "app/scopes_update", "s1", payload={"current": ["read_markets", "read_orders"]})

    _run(db, r.job_id)

    scope = db.execute(text('SELECT scope FROM "Session" WHERE shop = :s'), {"s": SHOP}).scalar()
    assert scope == "read_markets,read_orders"


@pytest.mark.integration
def test_scopes_update_still_runs_for_a_suspended_shop(db):
    tenant = _tenant(db)
    _session_row(db)
    tenant.status = TenantStatus.SUSPENDED
    db.commit()
    r = _ingest(db, "app/scopes_update", "s2", payload={"current": ["read_markets", "read_orders"]})

    _run(db, r.job_id)

    assert db.get(Tenant, tenant.id).scopes == "read_markets,read_orders"


# --- coalescing and the claim heartbeat --------------------------------------------------
@pytest.mark.integration
def test_a_coalesced_webhook_event_is_marked_processed(db):
    _tenant(db)
    first = _ingest(db, "markets/update", "c1", payload={"id": 1})
    second = _ingest(db, "markets/update", "c2", payload={"id": 2})

    assert first.job_id == second.job_id
    replaced = db.scalars(select(WebhookEvent).where(WebhookEvent.shopify_webhook_id == "c1")).one()
    assert replaced.status == WebhookEventStatus.PROCESSED
    assert replaced.error_message.startswith("coalesced into job")


@pytest.mark.integration
def test_a_heartbeat_keeps_a_long_job_from_being_reclaimed(db):
    tenant = _tenant(db)
    svc = AsyncJobService(db)
    job = svc.enqueue(tenant_id=tenant.id, operation=AsyncJobOperation.EXAMPLE_OP, topic="t", payload={})
    job.status = AsyncJobStatus.PROCESSING
    job.claimed_at = datetime.now(UTC) - timedelta(minutes=10)
    db.commit()

    svc.touch_claim(job.id)
    assert svc.reclaim_stale_processing_jobs(120) == 0
    db.refresh(job)
    assert job.status == AsyncJobStatus.PROCESSING


# --- app_subscriptions/update ------------------------------------------------------------
@pytest.mark.integration
def test_app_subscriptions_update_re_reads_the_plan(db, monkeypatch):
    from app.services import partner_billing_client

    tenant = _tenant(db)
    tenant.shopify_shop_id = 77
    db.commit()

    class FakeClient:
        configured = True

        def fetch_active_subscription(self, shop_gid):
            assert shop_gid == "gid://shopify/Shop/77"
            return PartnerSubscriptionSnapshot(has_active_contract=True, effective_plan_handle="light")

    monkeypatch.setattr(partner_billing_client, "PartnerBillingClient", FakeClient)
    r = _ingest(db, "app_subscriptions/update", "p1", payload={"app_subscription": {"status": "ACTIVE"}})
    assert db.get(AsyncJob, r.job_id).operation == AsyncJobOperation.SUBSCRIPTION_CHECK

    _run(db, r.job_id)

    assert BillingService(db).current_plan_handle(tenant.id) == "light"
