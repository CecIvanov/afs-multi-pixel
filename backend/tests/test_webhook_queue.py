"""Durable webhook queue: ingest dedup/coalesce, claim, retry/dead-letter, reaper,
and end-to-end processing of lifecycle + compliance webhooks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text

from app.models import AsyncJob, AsyncJobOperation, AsyncJobStatus, Tenant, TenantStatus
from app.services.async_job_service import AsyncJobService
from app.services.tenant_service import TenantService
from app.services.webhook_ingest_service import WebhookIngestService

SHOP = "queue-shop.myshopify.com"


def _make_tenant(db) -> Tenant:
    return TenantService(db).sync_shopify_install(SHOP, access_token="shpat_x", scopes="write_products")


def _ingest(db, topic, webhook_id="wh-1", payload=None):
    return WebhookIngestService(db).ingest(
        shop_domain=SHOP, topic=topic, shopify_webhook_id=webhook_id, payload=payload
    )


@pytest.mark.integration
def test_ingest_dedupes_on_webhook_id(db):
    _make_tenant(db)
    r1 = _ingest(db, "app/uninstalled", "dup-1")
    r2 = _ingest(db, "app/uninstalled", "dup-1")
    assert r1.status == "accepted"
    assert r2.status == "duplicate" and r2.duplicate is True


@pytest.mark.integration
def test_ingest_coalesces_pending_work(db):
    _make_tenant(db)
    _ingest(db, "app/scopes_update", "wh-a")
    _ingest(db, "app/scopes_update", "wh-b")  # different delivery id, same work
    jobs = db.scalars(
        select(AsyncJob).where(AsyncJob.operation == AsyncJobOperation.SCOPES_UPDATE)
    ).all()
    assert len(jobs) == 1  # coalesced by the pending-dedupe index


@pytest.mark.integration
def test_ingest_unknown_shop_idempotent_for_compliance(db):
    # No tenant created. Compliance/lifecycle topics must be accepted (ignored), not error.
    r = WebhookIngestService(db).ingest(shop_domain="ghost.myshopify.com", topic="shop/redact", shopify_webhook_id="g1")
    assert r.status == "ignored"


@pytest.mark.integration
def test_ingest_unknown_shop_raises_for_non_idempotent(db):
    with pytest.raises(ValueError):
        WebhookIngestService(db).ingest(shop_domain="ghost.myshopify.com", topic="app/scopes_update", shopify_webhook_id="g2")


@pytest.mark.integration
def test_claim_next_picks_highest_priority_and_marks_processing(db):
    tenant = _make_tenant(db)
    svc = AsyncJobService(db)
    # SHOP_INFO_FETCH (prio 10) was enqueued at install; add APP_UNINSTALL (prio 1000).
    _ingest(db, "app/uninstalled", "wh-c")
    claimed = svc.claim_next("worker-1")
    assert claimed is not None
    assert claimed.operation == AsyncJobOperation.APP_UNINSTALL  # highest priority first
    assert claimed.status == AsyncJobStatus.PROCESSING
    assert claimed.attempt_count == 1


@pytest.mark.integration
def test_retry_then_dead_letter(db):
    tenant = _make_tenant(db)
    svc = AsyncJobService(db)
    job = svc.enqueue(tenant_id=tenant.id, operation=AsyncJobOperation.EXAMPLE_OP, topic="t", payload={})
    job.max_attempts = 2
    job.attempt_count = 1
    db.commit()
    svc._retry_or_fail(job, "boom")  # attempt 1 < 2 -> reschedule
    db.refresh(job)
    assert job.status == AsyncJobStatus.PENDING and job.scheduled_at is not None

    job.attempt_count = 2
    db.commit()
    svc._retry_or_fail(job, "boom again")  # attempts exhausted -> dead-letter
    db.refresh(job)
    assert job.status == AsyncJobStatus.FAILED and job.finished_at is not None


@pytest.mark.integration
def test_reaper_requeues_stale_processing(db):
    tenant = _make_tenant(db)
    svc = AsyncJobService(db)
    job = svc.enqueue(tenant_id=tenant.id, operation=AsyncJobOperation.EXAMPLE_OP, topic="t")
    job.status = AsyncJobStatus.PROCESSING
    job.claimed_at = datetime.now(UTC) - timedelta(seconds=999)
    job.attempt_count = 1
    db.commit()
    reclaimed = svc.reclaim_stale_processing_jobs(older_than_seconds=120)
    assert reclaimed == 1
    db.refresh(job)
    assert job.status == AsyncJobStatus.PENDING  # requeued (attempts not exhausted)


@pytest.mark.integration
def test_process_app_uninstall_soft_uninstalls_tenant(db):
    tenant = _make_tenant(db)
    _ingest(db, "app/uninstalled", "wh-un")
    svc = AsyncJobService(db)
    # Process every pending job (uninstall first by priority).
    while (job := svc.claim_next("worker-1")) is not None:
        svc.process_job(job.id)
    db.expire_all()
    t = db.get(Tenant, tenant.id)
    assert t.status == TenantStatus.UNINSTALLED and t.access_token is None


@pytest.mark.integration
def test_process_shop_redact_hard_deletes_tenant(db):
    tenant = _make_tenant(db)
    tenant_id = tenant.id
    _ingest(db, "shop/redact", "wh-rd")
    svc = AsyncJobService(db)
    while (job := svc.claim_next("worker-1")) is not None:
        svc.process_job(job.id)
    db.expire_all()
    assert db.get(Tenant, tenant_id) is None  # hard-deleted


# --- the inbox contract (#3) -------------------------------------------------
def _quiet_tenant(db) -> Tenant:
    """A tenant without the install-time shop-info job (which would call Shopify)."""
    tenant = _make_tenant(db)
    db.execute(AsyncJob.__table__.delete().where(AsyncJob.tenant_id == tenant.id))
    db.commit()
    return tenant


def _drain(db) -> None:
    """Run every due job, the way the worker pool does."""
    svc = AsyncJobService(db)
    while (job := svc.claim_next("worker-1")) is not None:
        svc.process_job(job.id)


@pytest.fixture()
def failing_handler(monkeypatch):
    from app.services import job_processors

    calls: list[str] = []

    def boom(db, job):
        calls.append(str(job.id))
        raise RuntimeError("meta is down")

    monkeypatch.setitem(job_processors._REGISTRY, AsyncJobOperation.EXAMPLE_OP, boom)
    return calls


@pytest.mark.integration
def test_failing_job_retries_on_the_event_backoff_then_fails(db, failing_handler):
    from app.models import WebhookEvent, WebhookEventStatus

    tenant = _quiet_tenant(db)
    db.add(WebhookEvent(tenant_id=tenant.id, topic="t", shopify_webhook_id="wh-backoff", payload={}))
    db.commit()
    event = db.scalar(select(WebhookEvent).where(WebhookEvent.shopify_webhook_id == "wh-backoff"))
    svc = AsyncJobService(db)
    job = svc.enqueue(tenant_id=tenant.id, operation=AsyncJobOperation.EXAMPLE_OP, topic="t", webhook_event_id=event.id)

    delays = []
    while True:
        claimed = svc.claim_next("worker-1")
        assert claimed is not None and claimed.id == job.id
        svc.process_job(job.id)
        db.refresh(job)
        if job.status == AsyncJobStatus.FAILED:
            break
        delays.append(round((job.scheduled_at - datetime.now(UTC)).total_seconds()))
        assert svc.claim_next("worker-1") is None  # not due yet
        job.scheduled_at = datetime.now(UTC) - timedelta(seconds=1)  # fast-forward
        db.commit()

    assert delays == [60, 300, 1800, 7200, 21600]  # 1 min, 5 min, 30 min, 2 h, 6 h
    assert len(failing_handler) == 6  # first try + five retries
    db.refresh(event)
    assert event.status == WebhookEventStatus.FAILED


@pytest.mark.integration
def test_redelivered_webhook_is_stored_once_and_processed_once(db, monkeypatch):
    from app.models import WebhookEvent
    from app.services import job_processors

    _quiet_tenant(db)
    handled: list[str] = []
    monkeypatch.setitem(
        job_processors._REGISTRY, AsyncJobOperation.MARKETS_SYNC, lambda db, job: handled.append(job.topic)
    )

    _ingest(db, "markets/update", "redelivered-1")
    _drain(db)
    _ingest(db, "markets/update", "redelivered-1")  # Shopify redelivers after the first was processed
    _drain(db)

    assert db.scalar(select(func.count()).select_from(WebhookEvent)) == 1
    assert handled == ["markets/update"]


@pytest.mark.integration
@pytest.mark.parametrize(
    ("topic", "operation"),
    [
        ("APP_SCOPES_UPDATE", AsyncJobOperation.SCOPES_UPDATE),  # authenticate.webhook's storage form
        ("CUSTOMERS_DATA_REQUEST", AsyncJobOperation.CUSTOMER_DATA_REQUEST),
        ("orders/create", AsyncJobOperation.ORDERS_CREATE),
        ("markets/create", AsyncJobOperation.MARKETS_SYNC),
        ("markets/update", AsyncJobOperation.MARKETS_SYNC),
        ("markets/delete", AsyncJobOperation.MARKETS_SYNC),
    ],
)
def test_ingest_maps_topic_to_operation(db, topic, operation):
    _quiet_tenant(db)
    result = _ingest(db, topic, f"wh-{topic}", payload={"id": 1})
    assert result.status == "accepted"
    assert db.get(AsyncJob, result.job_id).operation == operation


@pytest.mark.integration
def test_orders_and_markets_jobs_complete_until_their_handlers_land(db):
    _quiet_tenant(db)
    _ingest(db, "orders/create", "wh-o1", payload={"id": 1001})
    _ingest(db, "markets/create", "wh-m1", payload={"id": 7})
    _drain(db)
    statuses = {
        j.operation: j.status
        for j in db.scalars(
            select(AsyncJob).where(
                AsyncJob.operation.in_([AsyncJobOperation.ORDERS_CREATE, AsyncJobOperation.MARKETS_SYNC])
            )
        )
    }
    assert statuses == {
        AsyncJobOperation.ORDERS_CREATE: AsyncJobStatus.COMPLETED,
        AsyncJobOperation.MARKETS_SYNC: AsyncJobStatus.COMPLETED,
    }


@pytest.mark.integration
def test_uninstall_deletes_capi_tokens_and_sessions_but_keeps_the_mapping(db):
    from app.models import MarketPixel

    tenant = _quiet_tenant(db)
    other = TenantService(db).sync_shopify_install("other-shop.myshopify.com", access_token="shpat_y")
    db.execute(AsyncJob.__table__.delete())
    for t in (tenant, other):
        db.add(MarketPixel(tenant_id=t.id, shopify_market_id=11, pixel_id="123456789012345", capi_token_encrypted="enc-token"))
    db.execute(
        text(
            """INSERT INTO "Session" (id, shop, state, "accessToken") VALUES
               ('offline_a', :a, 's', 'tok'), ('offline_b', :b, 's', 'tok')"""
        ),
        {"a": SHOP, "b": "other-shop.myshopify.com"},
    )
    db.commit()

    _ingest(db, "app/uninstalled", "wh-un-tokens")
    _drain(db)
    db.expire_all()

    pixels = {p.tenant_id: p for p in db.scalars(select(MarketPixel))}
    assert pixels[tenant.id].capi_token_encrypted is None
    assert pixels[tenant.id].pixel_id == "123456789012345"  # the rest waits for shop/redact
    assert pixels[other.id].capi_token_encrypted == "enc-token"
    shops = db.scalars(text('SELECT shop FROM "Session"')).all()
    assert shops == ["other-shop.myshopify.com"]


@pytest.mark.integration
def test_uninstall_processed_after_a_reinstall_leaves_the_new_install_alone(db):
    from app.models import MarketPixel

    tenant = _quiet_tenant(db)
    _ingest(db, "app/uninstalled", "wh-un-late")
    # The merchant reinstalls before the worker gets to the uninstall.
    tenant.installed_at = datetime.now(UTC) + timedelta(seconds=1)
    db.add(MarketPixel(tenant_id=tenant.id, shopify_market_id=11, pixel_id="123456789012345", capi_token_encrypted="enc"))
    db.execute(text("""INSERT INTO "Session" (id, shop, state, "accessToken") VALUES ('offline_new', :s, 's', 'tok')"""), {"s": SHOP})
    db.commit()

    _drain(db)
    db.expire_all()

    assert db.get(Tenant, tenant.id).status == TenantStatus.ACTIVE
    assert db.scalar(select(MarketPixel.capi_token_encrypted)) == "enc"
    assert db.scalars(text('SELECT id FROM "Session"')).all() == ["offline_new"]


@pytest.mark.integration
def test_processed_orders_create_keeps_no_raw_order_data(db):
    from app.models import WebhookEvent

    _quiet_tenant(db)
    result = _ingest(db, "orders/create", "wh-o-raw", payload={"id": 1001, "email": "a@b.c", "phone": "+359"})
    _drain(db)
    db.expire_all()

    assert db.get(AsyncJob, result.job_id).payload is None
    assert db.get(WebhookEvent, result.webhook_event_id).payload == {}
