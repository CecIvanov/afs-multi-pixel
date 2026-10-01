"""The Purchase join (spec §3.2 step 4, §7): the browser Purchase and orders/create
meet by order ID in either order; no browser Purchase, no Server Purchase; no raw
customer data stays in the database."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AsyncJob, PendingPurchase, ServerEvent, ServerEventStatus, WebhookEvent
from app.services.purchase_join import expire_pending_purchases, hash_order_customer, order_custom_data
from app.services.webhook_ingest_service import WebhookIngestService
from tests.test_markets import PIXEL, SHOP
from tests.test_relay import FakeMetaApi, _receive, _relay, _sender, _shop

ORDER_ID = 5551234
ORDER = {
    "id": ORDER_ID,
    "email": " Jane.Doe@Example.com ",
    "phone": "+359 88 123 4567",
    "created_at": "2026-10-01T10:00:00+03:00",
    "customer": {"id": 42, "first_name": "Jane", "last_name": "Doe"},
    "billing_address": {"first_name": "Jane", "last_name": "Doe", "city": "Sofia", "province_code": "22",
                        "zip": "1000", "country_code": "BG", "phone": "+359 88 123 4567"},
    "line_items": [{"product_id": 7, "quantity": 2}, {"product_id": 8, "quantity": 1}, {"product_id": 7, "quantity": 1}],
    "total_price": "30.00",
    "total_price_set": {"presentment_money": {"amount": "30.00", "currency_code": "EUR"}},
}
RAW_VALUES = ["Jane.Doe@Example.com", "jane.doe@example.com", "Jane", "Doe", "Sofia", "123 4567", "359881234567"]


def sha(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()


def _browser_purchase(db):
    return _receive(db, _relay(event="Purchase", eventId=f"purchase-{ORDER_ID}", orderId=str(ORDER_ID),
                               customData={"content_ids": ["7", "8"], "content_type": "product_group",
                                           "value": 30, "currency": "EUR", "order_id": str(ORDER_ID)}))


def _order_webhook(db, webhook_id="o-1"):
    from app.services.async_job_service import AsyncJobService

    WebhookIngestService(db).ingest(shop_domain=SHOP, topic="orders/create", shopify_webhook_id=webhook_id, payload=ORDER)
    svc = AsyncJobService(db)
    while (job := svc.claim_next("w")) is not None:
        svc.process_job(job.id)


@pytest.fixture()
def quiet_jobs(monkeypatch):
    """Only the orders/create handler runs; install-time Shopify jobs do nothing."""
    from app.models import AsyncJobOperation
    from app.services import job_processors

    for op in (AsyncJobOperation.SHOP_INFO_FETCH, AsyncJobOperation.MARKETS_SYNC,
               AsyncJobOperation.PIXEL_MAPPING_PUBLISH, AsyncJobOperation.STOREFRONT_HOSTS_SYNC):
        monkeypatch.setitem(job_processors._REGISTRY, op, lambda db, job: None)


def _purchase(db) -> ServerEvent:
    return db.scalar(select(ServerEvent).where(ServerEvent.event_id == f"purchase-{ORDER_ID}"))


@pytest.mark.unit
def test_customer_data_is_normalised_then_hashed():
    hashed = hash_order_customer(ORDER)

    assert hashed["em"] == sha("jane.doe@example.com")
    assert hashed["ph"] == sha("359881234567")
    assert hashed["fn"] == sha("jane") and hashed["ln"] == sha("doe")
    assert hashed["ct"] == sha("sofia") and hashed["zp"] == sha("1000") and hashed["country"] == sha("bg")
    assert hashed["external_id"] == sha("42")


@pytest.mark.unit
def test_purchase_custom_data_has_product_ids_and_the_presentment_total():
    assert order_custom_data(ORDER) == {
        "content_ids": ["7", "8"], "content_type": "product_group", "value": 30.0, "currency": "EUR",
        "num_items": 4, "order_id": str(ORDER_ID),
    }


@pytest.mark.integration
def test_browser_first_then_order_sends_one_hashed_server_purchase(db, quiet_jobs):
    _shop(db)
    _browser_purchase(db)
    assert _purchase(db).status == ServerEventStatus.WAITING

    _order_webhook(db)
    meta = FakeMetaApi()
    _sender(db, meta).send_due()

    ((pixel_id, body),) = meta.sent
    event = body["data"][0]
    assert pixel_id == PIXEL and event["event_id"] == f"purchase-{ORDER_ID}"
    assert event["user_data"]["em"] == sha("jane.doe@example.com")
    assert event["user_data"]["client_ip_address"] == "203.0.113.7"
    assert event["custom_data"]["value"] == 30.0
    assert _purchase(db).status == ServerEventStatus.SENT
    assert db.scalars(select(PendingPurchase)).all() == []


@pytest.mark.integration
def test_order_first_then_browser_joins_the_same_way(db, quiet_jobs):
    _shop(db)
    _order_webhook(db)
    assert _purchase(db) is None  # nothing to send without the browser half

    _browser_purchase(db)

    assert _purchase(db).status == ServerEventStatus.RECEIVED
    assert _purchase(db).payload["event"]["user_data"]["ph"] == sha("359881234567")


@pytest.mark.integration
def test_no_browser_purchase_means_no_server_purchase(db, quiet_jobs):
    _shop(db)

    _order_webhook(db)
    meta = FakeMetaApi()
    _sender(db, meta).send_due()

    assert meta.sent == []
    assert db.scalars(select(ServerEvent)).all() == []


@pytest.mark.integration
def test_no_raw_customer_data_remains_after_processing(db, quiet_jobs):
    _shop(db)
    _order_webhook(db)  # waits in PendingPurchase, hashed

    dump = json.dumps(
        [p.hashed_customer_data for p in db.scalars(select(PendingPurchase))]
        + [w.payload for w in db.scalars(select(WebhookEvent))]
        + [j.payload for j in db.scalars(select(AsyncJob))]
    )
    for raw in RAW_VALUES:
        assert raw not in dump

    _browser_purchase(db)
    _sender(db, FakeMetaApi()).send_due()
    assert _purchase(db).payload["event"]["user_data"] == {}


@pytest.mark.integration
def test_unmatched_halves_expire_after_seven_days(db, quiet_jobs):
    _shop(db)
    _browser_purchase(db)
    pending = db.scalar(select(PendingPurchase))
    pending.created_at = datetime.now(UTC) - timedelta(days=8)
    db.commit()

    assert expire_pending_purchases(db) == 1

    assert db.scalars(select(PendingPurchase)).all() == []
    assert _purchase(db).status == ServerEventStatus.FAILED
