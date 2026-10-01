"""Celery tasks — cron/maintenance only (the durable job queue handles webhook
work). Each task opens its own DB session, logs, and closes it.
"""

from __future__ import annotations

from app.db.session import SessionLocal
from app.logging_config import get_logger
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.heartbeat")
def heartbeat() -> dict[str, str]:
    logger = get_logger()
    db = SessionLocal()
    try:
        logger.info("worker.heartbeat.completed")
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        logger.error("worker.heartbeat.failed", exc)
        raise
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.purge_job_retention")
def purge_job_retention() -> dict[str, int]:
    from app.services.async_job_service import AsyncJobService

    db = SessionLocal()
    try:
        return AsyncJobService(db).purge_retention()
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.purge_webhook_retention")
def purge_webhook_retention() -> dict[str, int]:
    from app.services.webhook_event_service import WebhookEventService

    db = SessionLocal()
    try:
        return {"deleted": WebhookEventService(db).purge_retention()}
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.dispatch_shopify_token_refresh")
def dispatch_shopify_token_refresh() -> dict[str, int]:
    """Beat entry: find tenants whose Shopify offline token is nearing expiry and
    enqueue a durable token_refresh job for each. The actual OAuth exchange runs in
    the job pool, so this returns fast and never blocks on Shopify."""
    from app.services.shopify_token_refresh_service import ShopifyTokenRefreshService

    logger = get_logger()
    db = SessionLocal()
    try:
        payload = ShopifyTokenRefreshService(db).discover_and_enqueue_refreshes()
        logger.info("worker.token_refresh_dispatch.completed", payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        logger.error("worker.token_refresh_dispatch.failed", exc)
        raise
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.dispatch_billing_reconcile")
def dispatch_billing_reconcile() -> dict[str, int]:
    """Drift reconcile: re-check every active tenant against the Partner API so plan
    changes made outside the app are caught. Requires the Partner API to be
    configured + PartnerBillingClient.fetch_active_subscription implemented."""
    from sqlalchemy import select

    from app.models import BillingReconcileSource, Tenant, TenantStatus
    from app.services.billing_reconcile_service import BillingReconcileService
    from app.services.partner_billing_client import PartnerBillingClient

    logger = get_logger()
    client = PartnerBillingClient()
    if not client.configured:
        logger.info("billing.reconcile_dispatch.skipped", {"reason": "partner_api_unconfigured"})
        return {"reconciled": 0}

    db = SessionLocal()
    reconciled = 0
    try:
        shops = db.scalars(select(Tenant.shop_domain).where(Tenant.status == TenantStatus.ACTIVE)).all()
        for shop in shops:
            try:
                snapshot = client.fetch_active_subscription(shop)
                if snapshot is None:
                    continue
                BillingReconcileService(db).reconcile(shop, snapshot, BillingReconcileSource.SCHEDULED_WORKER)
                reconciled += 1
            except NotImplementedError:
                break  # template stub — implement the Partner API fetch to enable
            except Exception as exc:  # noqa: BLE001 — one shop must not stop the sweep
                logger.warn("billing.reconcile_dispatch.shop_failed", {"shop": shop, "detail": str(exc)})
        return {"reconciled": reconciled}
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.dispatch_storefront_hosts_sync")
def dispatch_storefront_hosts_sync() -> dict[str, int]:
    """Daily: queue a storefront host re-fetch for every installed shop, so a new
    custom domain reaches the Relay allowlist within a day."""
    from sqlalchemy import select

    from app.models import AsyncJobOperation, Tenant, TenantStatus
    from app.services.async_job_service import AsyncJobService

    logger = get_logger()
    db = SessionLocal()
    try:
        jobs = AsyncJobService(db)
        tenants = db.scalars(select(Tenant).where(Tenant.status == TenantStatus.ACTIVE)).all()
        for tenant in tenants:
            jobs.enqueue(tenant_id=tenant.id, operation=AsyncJobOperation.STOREFRONT_HOSTS_SYNC, topic="daily/hosts")
        logger.info("worker.storefront_hosts_dispatch.completed", {"shops": len(tenants)})
        return {"shops": len(tenants)}
    finally:
        db.close()
