"""Durable webhook queue: ingest dedup/coalesce, claim, retry/dead-letter, reaper,
and end-to-end processing of lifecycle + compliance webhooks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

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
