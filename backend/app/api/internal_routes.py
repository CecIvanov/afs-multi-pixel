"""Internal API — called only by the Node BFF, guarded by the X-Internal-Key
shared secret. Never expose these to the internet.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, verify_internal_key
from app.schemas import (
    BillingOut,
    BillingReconcileIn,
    BillingReconcileOut,
    MarketOut,
    MarketsOut,
    PixelCheckIn,
    PixelCheckOut,
    PixelSaveIn,
    ShopifyInstallIn,
    ShopifySessionSyncIn,
    TenantOut,
    WebhookIngestIn,
    WebhookIngestOut,
    tenant_to_out,
)
from app.logging_config import get_logger
from app.models import Tenant
from app.services.market_service import MarketService, MarketView, PixelValidationError
from app.services.tenant_service import TenantService
from app.services.webhook_ingest_service import WebhookIngestService

logger = get_logger().child({"component": "internal_routes"})

router = APIRouter(
    prefix="/api/v1/internal",
    tags=["Internal"],
    dependencies=[Depends(verify_internal_key)],
)


@router.post("/shopify/install", response_model=TenantOut)
def shopify_install(payload: ShopifyInstallIn, db: Session = Depends(get_db)) -> TenantOut:
    try:
        tenant = TenantService(db).sync_shopify_install(
            payload.shop_domain,
            access_token=payload.access_token,
            scopes=payload.scopes,
            refresh_token=payload.refresh_token,
            access_token_expires_at=payload.access_token_expires_at,
            refresh_token_expires_at=payload.refresh_token_expires_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return tenant_to_out(tenant, db)


@router.post("/shopify/session-sync", response_model=TenantOut)
def shopify_session_sync(payload: ShopifySessionSyncIn, db: Session = Depends(get_db)) -> TenantOut:
    try:
        tenant = TenantService(db).sync_shopify_session(
            payload.shop_domain,
            access_token=payload.access_token,
            scopes=payload.scopes,
            refresh_token=payload.refresh_token,
            access_token_expires_at=payload.access_token_expires_at,
            refresh_token_expires_at=payload.refresh_token_expires_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return tenant_to_out(tenant, db)


@router.post("/shopify/webhooks/ingest", response_model=WebhookIngestOut)
def shopify_webhook_ingest(payload: WebhookIngestIn, db: Session = Depends(get_db)) -> WebhookIngestOut:
    """Record a verified webhook + enqueue its durable job. All lifecycle/compliance
    webhooks (uninstall, redact, scopes) flow through here — processed out-of-band
    by the job pool, so this returns in ms."""
    try:
        result = WebhookIngestService(db).ingest(
            shop_domain=payload.shop_domain,
            topic=payload.topic,
            shopify_webhook_id=payload.shopify_webhook_id,
            payload=payload.payload,
            webhook_context=payload.webhook_context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return WebhookIngestOut(
        status=result.status,
        duplicate=result.duplicate,
        job_id=result.job_id,
        webhook_event_id=result.webhook_event_id,
    )


@router.get("/tenants/by-shop/{shop_domain}", response_model=TenantOut)
def get_tenant_by_shop(shop_domain: str, db: Session = Depends(get_db)) -> TenantOut:
    tenant = TenantService(db).get_tenant_by_shop_domain(shop_domain)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant_to_out(tenant, db)


@router.post("/billing/reconcile", response_model=BillingReconcileOut)
def billing_reconcile(payload: BillingReconcileIn, db: Session = Depends(get_db)) -> BillingReconcileOut:
    """Reconcile the tenant's subscription against a Partner-API snapshot (passed
    by the Node app on app load, or by the scheduled worker)."""
    from app.models import BillingReconcileSource
    from app.services.billing_reconcile_service import BillingReconcileService
    from app.services.partner_billing_client import PartnerSubscriptionSnapshot

    snap = payload.partner_snapshot
    snapshot = PartnerSubscriptionSnapshot(
        has_active_contract=snap.has_active_contract,
        effective_plan_handle=snap.effective_plan_handle,
        pending_plan_handle=snap.pending_plan_handle,
        billing_period=snap.billing_period,
        cancel_at_end_of_cycle=snap.cancel_at_end_of_cycle,
        cycle_start=snap.cycle_start,
        cycle_end=snap.cycle_end,
        legacy_subscription_id=snap.legacy_subscription_id,
        trial_ends_at=snap.trial_ends_at,
    )
    try:
        source = BillingReconcileSource(payload.source)
    except ValueError:
        source = BillingReconcileSource.APP_LOAD
    try:
        result = BillingReconcileService(db).reconcile(payload.shop_domain, snapshot, source)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return BillingReconcileOut(
        status="ok",
        action=result.action.value,
        effective_plan_handle=result.effective_plan_handle,
        pending_plan_handle=result.pending_plan_handle,
    )


@router.get("/tenants/by-shop/{shop_domain}/billing", response_model=BillingOut)
def get_billing_by_shop(shop_domain: str, db: Session = Depends(get_db)) -> BillingOut:
    from app.billing.entitlements import _feature_min_rank
    from app.billing.plan_catalog import plan_by_handle
    from app.services.billing_service import BillingService

    tenant = TenantService(db).get_tenant_by_shop_domain(shop_domain)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    billing = BillingService(db)
    handle = billing.current_plan_handle(tenant.id)
    plan = plan_by_handle(handle)
    sub = billing.get_subscription(tenant.id)
    pending = None
    if sub and sub.pending_billing_plan_id:
        from app.models import BillingPlan

        p = db.get(BillingPlan, sub.pending_billing_plan_id)
        pending = p.handle if p else None
    counter = billing._ensure_counter(tenant.id)
    return BillingOut(
        plan_handle=handle,
        plan_name=plan.name if plan else handle,
        pending_plan_handle=pending,
        status=sub.status.value if sub else "none",
        used=counter.used,
        quota=plan.monthly_quota if plan else None,
        supports={feat: billing.has_feature(tenant.id, feat) for feat in _feature_min_rank()},
    )


# --- Markets and the Pixel Mapping (the Market health page) ------------------------
def get_market_service(db: Session = Depends(get_db)) -> MarketService:
    return MarketService(db)


def _tenant_or_404(db: Session, shop_domain: str) -> Tenant:
    tenant = TenantService(db).get_tenant_by_shop_domain(shop_domain)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


def _market_out(view: MarketView) -> MarketOut:
    return MarketOut.model_validate(asdict(view))


@router.get("/tenants/by-shop/{shop_domain}/markets", response_model=MarketsOut)
def list_markets(
    shop_domain: str,
    sync: bool = False,
    db: Session = Depends(get_db),
    markets: MarketService = Depends(get_market_service),
) -> MarketsOut:
    """The shop's Markets with their Market Pixels. ``sync=true`` (app open)
    re-fetches them from Shopify first; if that fails the stored list is returned
    with ``sync_error`` set, so the page still renders."""
    tenant = _tenant_or_404(db, shop_domain)
    sync_error = None
    if sync:
        try:
            return MarketsOut(markets=[_market_out(v) for v in markets.sync(tenant)])
        except Exception as exc:  # noqa: BLE001 — a failed re-fetch must not break the page
            db.rollback()
            sync_error = str(exc)[:500]
            logger.warn("markets.sync_on_open_failed", {"shop": shop_domain, "detail": sync_error})
    return MarketsOut(markets=[_market_out(v) for v in markets.list_markets(tenant)], sync_error=sync_error)


@router.post("/tenants/by-shop/{shop_domain}/markets/{market_id}/pixel/check", response_model=PixelCheckOut)
def check_market_pixel(
    shop_domain: str,
    market_id: int,
    payload: PixelCheckIn,
    db: Session = Depends(get_db),
    markets: MarketService = Depends(get_market_service),
) -> PixelCheckOut:
    tenant = _tenant_or_404(db, shop_domain)
    try:
        check = markets.check_pixel(tenant, market_id, pixel_id=payload.pixel_id, token=payload.token)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PixelValidationError as exc:
        return PixelCheckOut(ok=False, error=str(exc))
    return PixelCheckOut(**asdict(check))


@router.put("/tenants/by-shop/{shop_domain}/markets/{market_id}/pixel", response_model=MarketOut)
def save_market_pixel(
    shop_domain: str,
    market_id: int,
    payload: PixelSaveIn,
    db: Session = Depends(get_db),
    markets: MarketService = Depends(get_market_service),
) -> MarketOut:
    tenant = _tenant_or_404(db, shop_domain)
    try:
        view = markets.save_pixel(
            tenant, market_id, pixel_id=payload.pixel_id, token=payload.token, test_event_code=payload.test_event_code
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PixelValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _market_out(view)


@router.delete("/tenants/by-shop/{shop_domain}/markets/{market_id}/pixel", response_model=MarketOut)
def remove_market_pixel(
    shop_domain: str,
    market_id: int,
    db: Session = Depends(get_db),
    markets: MarketService = Depends(get_market_service),
) -> MarketOut:
    tenant = _tenant_or_404(db, shop_domain)
    try:
        return _market_out(markets.remove_pixel(tenant, market_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
