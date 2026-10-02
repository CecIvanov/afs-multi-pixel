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


@celery_app.task(name="app.workers.tasks.dispatch_subscription_check")
def dispatch_subscription_check() -> dict[str, int]:
    """Daily: re-read every shop's subscription to the one plan from the Partner
    API, so a cancellation made outside the app stops its Relays (spec §5)."""
    from app.services.subscription_service import check_all_subscriptions

    db = SessionLocal()
    try:
        return check_all_subscriptions(db)
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


@celery_app.task(name="app.workers.tasks.daily_retention")
def daily_retention() -> dict[str, int]:
    from app.services.retention_service import run_daily_retention

    db = SessionLocal()
    try:
        return run_daily_retention(db)
    except Exception as exc:  # noqa: BLE001
        get_logger().error("worker.daily_retention.failed", exc)
        raise
    finally:
        db.close()
