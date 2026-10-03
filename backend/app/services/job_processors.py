"""Operation -> handler registry for the durable job queue.

Register a handler with @job_handler(AsyncJobOperation.X); dispatch_job looks it
up. A handler raising propagates to AsyncJobService._retry_or_fail (retry/backoff
/ dead-letter). Add your app's operations + handlers here.
"""

from __future__ import annotations

from typing import Callable

from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import AsyncJob, AsyncJobOperation

logger = get_logger().child({"component": "job_processors"})

JobHandler = Callable[[Session, AsyncJob], None]
_REGISTRY: dict[AsyncJobOperation, JobHandler] = {}


def job_handler(operation: AsyncJobOperation) -> Callable[[JobHandler], JobHandler]:
    def register(fn: JobHandler) -> JobHandler:
        _REGISTRY[operation] = fn
        return fn

    return register


def dispatch_job(db: Session, job: AsyncJob) -> None:
    handler = _REGISTRY.get(job.operation)
    if handler is None:
        raise ValueError(f"No handler registered for operation {job.operation.value}")
    if job.shopify_webhook_id and not _tenant_takes_webhook(db, job):
        # Stored and answered 200 at ingest; an uninstalled shop gets only its
        # lifecycle/compliance work.
        logger.info("job.skipped_inactive_tenant", {"jobId": str(job.id), "operation": job.operation.value})
        return
    handler(db, job)


def _tenant_takes_webhook(db: Session, job: AsyncJob) -> bool:
    from app.models import Tenant, TenantStatus
    from app.services.webhook_ingest_service import INACTIVE_TENANT_ALLOWED_OPERATIONS

    tenant = db.get(Tenant, job.tenant_id)
    if tenant is None:
        return False
    return tenant.status == TenantStatus.ACTIVE or job.operation in INACTIVE_TENANT_ALLOWED_OPERATIONS


def _shop_domain(db: Session, job: AsyncJob) -> str:
    from app.models import Tenant

    tenant = db.get(Tenant, job.tenant_id)
    return tenant.shop_domain if tenant else ""


# --- handlers ---------------------------------------------------------------
@job_handler(AsyncJobOperation.APP_UNINSTALL)
def _handle_app_uninstall(db: Session, job: AsyncJob) -> None:
    from app.models import Tenant
    from app.services.async_job_service import AsyncJobService
    from app.services.shopify_session_service import ShopifySessionService
    from app.services.tenant_service import TenantService

    tenant = db.get(Tenant, job.tenant_id)
    if tenant is None:
        return
    if tenant.installed_at and job.created_at and tenant.installed_at > job.created_at:
        # Reinstalled after this webhook arrived: its sessions and tokens are new.
        logger.info("job.app_uninstall.superseded_by_reinstall", {"jobId": str(job.id), "tenantId": str(tenant.id)})
        return
    shop = tenant.shop_domain
    # Drop this tenant's other pending jobs so a dead tenant can't hold slots.
    AsyncJobService(db).purge_tenant_active_jobs(job.tenant_id)
    # Drops the Shopify and Conversions API tokens; an uninstalled tenant's
    # Relays are refused. Everything else waits for shop/redact.
    TenantService(db).sync_shopify_uninstall(shop)
    ShopifySessionService(db).delete_shop_sessions(shop)


@job_handler(AsyncJobOperation.SHOP_REDACT)
def _handle_shop_redact(db: Session, job: AsyncJob) -> None:
    from app.services.compliance_service import ComplianceService

    ComplianceService(db).redact_shop_data(_shop_domain(db, job))


@job_handler(AsyncJobOperation.CUSTOMER_DATA_REQUEST)
def _handle_customer_data_request(db: Session, job: AsyncJob) -> None:
    from app.services.compliance_service import ComplianceService

    payload = job.payload or {}
    customer = payload.get("customer") or {}
    ComplianceService(db).export_customer_data(
        shop_domain=_shop_domain(db, job),
        shopify_customer_id=customer.get("id"),
        orders_requested=payload.get("orders_requested"),
    )


@job_handler(AsyncJobOperation.CUSTOMER_REDACT)
def _handle_customer_redact(db: Session, job: AsyncJob) -> None:
    from app.services.compliance_service import ComplianceService

    payload = job.payload or {}
    customer = payload.get("customer") or {}
    ComplianceService(db).redact_customer_data(
        shop_domain=_shop_domain(db, job),
        orders_to_redact=payload.get("orders_to_redact") or [],
        shopify_customer_id=customer.get("id"),
    )


@job_handler(AsyncJobOperation.SCOPES_UPDATE)
def _handle_scopes_update(db: Session, job: AsyncJob) -> None:
    """Persist the new scopes with the shop's stored offline token (the Prisma
    Session row); the webhook route only stores the webhook."""
    from app.services.shopify_session_service import ShopifySessionService
    from app.services.tenant_service import TenantService

    shop = _shop_domain(db, job)
    payload = job.payload or {}
    ctx = payload.get("webhook_context") or {}  # jobs queued before the route stopped sending it
    stored = ShopifySessionService(db).get_offline_session(shop) or {}
    access_token = ctx.get("access_token") or stored.get("access_token")
    if not access_token:
        return  # nothing to persist without the session token
    current = payload.get("current")
    scopes = ",".join(current) if isinstance(current, list) else ctx.get("scopes") or stored.get("scopes")
    TenantService(db).sync_shopify_session(
        shop,
        access_token=access_token,
        scopes=scopes,
        refresh_token=ctx.get("refresh_token") or stored.get("refresh_token"),
    )


@job_handler(AsyncJobOperation.SHOP_INFO_FETCH)
def _handle_shop_info_fetch(db: Session, job: AsyncJob) -> None:
    from app.models import Tenant
    from app.services.shopify_shop_info_service import execute_shop_info_fetch_for_tenant

    tenant = db.get(Tenant, job.tenant_id)
    if tenant is not None:
        execute_shop_info_fetch_for_tenant(db, tenant)


@job_handler(AsyncJobOperation.TOKEN_REFRESH)
def _handle_token_refresh(db: Session, job: AsyncJob) -> None:
    """Refresh a tenant's expiring Shopify offline token. Enqueued proactively by
    the beat (before expiry) and reactively on a 401. A dead refresh chain marks
    the tenant revoked and raises (retry/backoff finds nothing left to do)."""
    from app.models import Tenant
    from app.services.shopify_token_refresh_service import ShopifyTokenRefreshService

    tenant = db.get(Tenant, job.tenant_id)
    if tenant is None:
        return
    ShopifyTokenRefreshService(db).refresh_tenant_tokens(tenant, reason=job.topic or "token_refresh")


@job_handler(AsyncJobOperation.ORDERS_CREATE)
def _handle_orders_create(db: Session, job: AsyncJob) -> None:
    """The order half of the Purchase join. The customer data is hashed into
    PendingPurchase, then the raw order is wiped from the job and the inbox row
    (spec §7): no raw order data outlives processing."""
    from app.models import Tenant, WebhookEvent
    from app.services.purchase_join import PurchaseJoin

    order = dict(job.payload or {})
    order.pop("webhook_context", None)
    tenant = db.get(Tenant, job.tenant_id)
    if tenant is not None and order:
        PurchaseJoin(db).record_order(tenant, order)
    job.payload = None
    if job.webhook_event_id and (event := db.get(WebhookEvent, job.webhook_event_id)) is not None:
        event.payload = {}


@job_handler(AsyncJobOperation.MARKETS_SYNC)
def _handle_markets_sync(db: Session, job: AsyncJob) -> None:
    """Re-fetch the shop's Markets. The markets/* payloads are too thin to apply,
    so every change (and install) runs the same full sync."""
    from app.services.market_service import MarketService

    if (tenant := _admin_ready_tenant(db, job)) is not None:
        MarketService(db).sync(tenant)


def _admin_ready_tenant(db: Session, job: AsyncJob):
    from app.models import Tenant
    from app.services.shopify_tenant_credentials import tenant_can_call_admin_api

    tenant = db.get(Tenant, job.tenant_id)
    return tenant if tenant is not None and tenant_can_call_admin_api(tenant) else None


@job_handler(AsyncJobOperation.PIXEL_MAPPING_PUBLISH)
def _handle_pixel_mapping_publish(db: Session, job: AsyncJob) -> None:
    from app.services.storefront_publisher import StorefrontPublisher

    if (tenant := _admin_ready_tenant(db, job)) is not None:
        StorefrontPublisher(db).publish(tenant)


@job_handler(AsyncJobOperation.STOREFRONT_HOSTS_SYNC)
def _handle_storefront_hosts_sync(db: Session, job: AsyncJob) -> None:
    from app.services.storefront_publisher import StorefrontPublisher

    if (tenant := _admin_ready_tenant(db, job)) is not None:
        StorefrontPublisher(db).sync_storefront_hosts(tenant)


@job_handler(AsyncJobOperation.EXAMPLE_OP)
def _handle_example(db: Session, job: AsyncJob) -> None:
    logger.info("job.example", {"jobId": str(job.id), "tenantId": str(job.tenant_id)})
