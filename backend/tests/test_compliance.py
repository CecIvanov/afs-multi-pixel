"""GDPR: shop redaction (hard delete of every tenant-scoped row), customer
redaction by order ID, and the fixed data-request reply."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select

from app.models import (
    AsyncJob,
    AsyncJobOperation,
    BillingReconcileSource,
    BillingSubscriptionEvent,
    BillingSubscriptionEventType,
    MarketPixel,
    PendingPurchase,
    ServerEvent,
    ServerEventSource,
    Tenant,
    TenantMetadata,
    TenantSubscription,
    UsageCounter,
    WebhookEvent,
)
from app.services.async_job_service import AsyncJobService
from app.services.compliance_service import DATA_REQUEST_REPLY, ComplianceService
from app.services.tenant_service import TenantService
from app.services.webhook_ingest_service import WebhookIngestService

SHOP = "redact-shop.myshopify.com"


def _tenant(db, shop: str = SHOP) -> Tenant:
    tenant = TenantService(db).sync_shopify_install(shop, access_token="tok")
    db.execute(AsyncJob.__table__.delete().where(AsyncJob.tenant_id == tenant.id))  # no Shopify calls
    db.commit()
    return tenant


def _event(tenant: Tenant, event_id: str) -> ServerEvent:
    return ServerEvent(
        tenant_id=tenant.id,
        source=ServerEventSource.RELAY,
        event_name="Purchase" if event_id.startswith("purchase-") else "AddToCart",
        event_id=event_id,
        shopify_market_id=11,
        pixel_id="123456789012345",
        marketing_consent=True,
        payload={},
    )


def _drain(db) -> None:
    svc = AsyncJobService(db)
    while (job := svc.claim_next("worker-1")) is not None:
        svc.process_job(job.id)


def _count(db, model, tenant_id) -> int:
    return db.scalar(select(func.count()).select_from(model).where(model.tenant_id == tenant_id))


@pytest.mark.integration
def test_redact_shop_data_deletes_all_tenant_rows(db):
    tenant = _tenant(db)
    tid = tenant.id
    db.add(TenantMetadata(tenant_id=tid, m_key="store_name", m_value="Demo"))
    db.add(WebhookEvent(tenant_id=tid, topic="shop/redact", shopify_webhook_id="w-red", payload={}))
    db.add(MarketPixel(tenant_id=tid, shopify_market_id=11, pixel_id="123456789012345", capi_token_encrypted="enc"))
    db.add(_event(tenant, "purchase-1"))
    db.add(PendingPurchase(tenant_id=tid, order_id=1, browser_half={"fbp": "fb.1"}))
    db.add(UsageCounter(tenant_id=tid, period_start=date(2026, 10, 1), used=0, quota=0))
    db.add(
        BillingSubscriptionEvent(
            tenant_id=tid,
            event_type=BillingSubscriptionEventType.INITIAL_SELECTION,
            effective_plan_handle="free",
            source=BillingReconcileSource.APP_LOAD,
        )
    )
    db.commit()

    assert _count(db, TenantSubscription, tid) == 1

    ok = ComplianceService(db).redact_shop_data(SHOP)
    assert ok is True

    assert db.get(Tenant, tid) is None
    for model in (
        TenantMetadata, TenantSubscription, WebhookEvent, AsyncJob, MarketPixel, ServerEvent, PendingPurchase,
        UsageCounter, BillingSubscriptionEvent,
    ):
        assert _count(db, model, tid) == 0, model.__tablename__


@pytest.mark.integration
def test_redact_unknown_shop_is_ignored(db):
    assert ComplianceService(db).redact_shop_data("nobody.myshopify.com") is False


@pytest.mark.integration
def test_customers_redact_deletes_rows_for_the_listed_orders_only(db):
    tenant = _tenant(db)
    other = _tenant(db, "other-shop.myshopify.com")
    db.add_all(
        [
            _event(tenant, "purchase-1001"),
            _event(tenant, "purchase-1002"),
            _event(tenant, "purchase-2000"),  # not listed
            _event(tenant, "atc-abc"),  # not tied to an order
            _event(other, "purchase-1001"),  # same order ID, other shop
            PendingPurchase(tenant_id=tenant.id, order_id=1001, browser_half={}),
            PendingPurchase(tenant_id=tenant.id, order_id=2000, browser_half={}),
            PendingPurchase(tenant_id=other.id, order_id=1001, browser_half={}),
        ]
    )
    db.commit()
    # A raw orders/create still waiting in the inbox holds the customer's data too.
    WebhookIngestService(db).ingest(
        shop_domain=SHOP, topic="orders/create", shopify_webhook_id="o-1001", payload={"id": 1001, "email": "a@b.c"}
    )
    WebhookIngestService(db).ingest(
        shop_domain=SHOP, topic="orders/create", shopify_webhook_id="o-2000", payload={"id": 2000}
    )

    WebhookIngestService(db).ingest(
        shop_domain=SHOP,
        topic="customers/redact",
        shopify_webhook_id="cr-1",
        payload={"customer": {"id": 5, "email": "a@b.c"}, "orders_to_redact": [1001, 1002]},
    )
    _drain(db)

    remaining = sorted((str(e.tenant_id == tenant.id), e.event_id) for e in db.scalars(select(ServerEvent)))
    assert remaining == [("False", "purchase-1001"), ("True", "atc-abc"), ("True", "purchase-2000")]
    pending = sorted((p.tenant_id == tenant.id, p.order_id) for p in db.scalars(select(PendingPurchase)))
    assert pending == [(False, 1001), (True, 2000)]
    inbox = db.scalars(select(WebhookEvent.shopify_webhook_id).where(WebhookEvent.topic == "orders/create")).all()
    assert inbox == ["o-2000"]
    order_jobs = db.scalars(select(AsyncJob).where(AsyncJob.operation == AsyncJobOperation.ORDERS_CREATE)).all()
    assert [j.dedupe_key for j in order_jobs] == ["orders_create:2000"]


@pytest.mark.integration
def test_two_redacts_for_one_customer_both_apply(db):
    tenant = _tenant(db)
    db.add_all([PendingPurchase(tenant_id=tenant.id, order_id=o, browser_half={}) for o in (1, 2)])
    db.commit()
    for webhook_id, orders in (("cr-a", [1]), ("cr-b", [2])):
        WebhookIngestService(db).ingest(
            shop_domain=SHOP,
            topic="customers/redact",
            shopify_webhook_id=webhook_id,
            payload={"customer": {"id": 5}, "orders_to_redact": orders},
        )
    _drain(db)
    assert _count(db, PendingPurchase, tenant.id) == 0


@pytest.mark.integration
def test_customers_data_request_gets_the_fixed_reply_and_deletes_nothing(db):
    tenant = _tenant(db)
    db.add(PendingPurchase(tenant_id=tenant.id, order_id=1001, browser_half={}))
    db.commit()

    reply = ComplianceService(db).export_customer_data(
        shop_domain=SHOP, shopify_customer_id=5, orders_requested=[1001]
    )

    assert reply["reply"] == DATA_REQUEST_REPLY
    assert reply["records"] == []
    assert _count(db, PendingPurchase, tenant.id) == 1
