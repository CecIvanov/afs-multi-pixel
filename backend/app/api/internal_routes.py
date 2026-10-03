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
    EventPageOut,
    MarketDetailOut,
    MarketOut,
    MarketPageOut,
    MarketsOut,
    MarketStatsOut,
    RelayIn,
    RelayOut,
    SetupIn,
    SetupOut,
    SummaryOut,
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


def _mark_authenticated(db: Session, tenant) -> None:
    """The app just authenticated with a live Shopify session: an app/uninstalled
    triggered before now is stale (see job_processors._handle_app_uninstall)."""
    from sqlalchemy import func

    tenant.last_authenticated_at = func.now()
    db.commit()
    db.refresh(tenant)


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
    _mark_authenticated(db, tenant)
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
    _mark_authenticated(db, tenant)
    return tenant_to_out(tenant, db)


@router.post("/shopify/webhooks/ingest", response_model=WebhookIngestOut)
def shopify_webhook_ingest(payload: WebhookIngestIn, db: Session = Depends(get_db)) -> WebhookIngestOut:
    """Store a verified webhook and enqueue its job — always, so Shopify gets its
    200; the worker decides what to do with it. Returns in ms."""
    result = WebhookIngestService(db).ingest(
        shop_domain=payload.shop_domain,
        topic=payload.topic,
        shopify_webhook_id=payload.shopify_webhook_id,
        payload=payload.payload,
        webhook_context=payload.webhook_context,
        triggered_at=payload.triggered_at,
    )
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
    by the Node app on app load, or by the scheduled worker), plus the plan handle
    from Shopify's redirect right after the merchant picks a plan."""
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
    from app.billing.plan_catalog import free_plan_handle
    from app.services.relay_service import numeric_id

    tenant = _tenant_or_404(db, payload.shop_domain)
    if payload.shop_gid and (shop_id := numeric_id(payload.shop_gid)) is not None:
        tenant.shopify_shop_id = shop_id
        db.commit()
    hint = payload.redirect_hint.plan_handle if payload.redirect_hint else None
    result = BillingReconcileService(db).reconcile(
        payload.shop_domain, snapshot, source, redirect_plan_handle=(hint or "").strip().lower() or None
    )
    return BillingReconcileOut(
        status="ok",
        action=result.action.value,
        effective_plan_handle=result.effective_plan_handle,
        pending_plan_handle=result.pending_plan_handle,
        subscribed=result.effective_plan_handle != free_plan_handle(),
    )


@router.get("/tenants/by-shop/{shop_domain}/billing", response_model=BillingOut)
def get_billing_by_shop(shop_domain: str, db: Session = Depends(get_db)) -> BillingOut:
    from app.billing.entitlements import _feature_min_rank
    from app.billing.plan_catalog import free_plan_handle, plan_by_handle
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
        pending_plan_name=(p.name if (p := plan_by_handle(pending)) else pending) if pending else None,
        current_period_end=sub.current_period_end if sub else None,
        subscribed=handle != free_plan_handle(),
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


def _setup_out(tenant: Tenant) -> SetupOut:
    return SetupOut(
        consent_confirmed=tenant.consent_confirmed_at is not None,
        verified_in_meta=tenant.verified_in_meta_at is not None,
    )


def _markets_out(db: Session, tenant: Tenant, views: list[MarketView], sync_error: str | None = None) -> MarketsOut:
    from app.services.event_stats import market_stats

    stats = market_stats(db, tenant)
    markets = []
    for view in views:
        out = _market_out(view)
        if (s := stats.markets.get(view.shopify_market_id)) is not None:
            out.stats = MarketStatsOut(**asdict(s))
        markets.append(out)
    return MarketsOut(
        markets=markets,
        summary=SummaryOut(browser_24h=stats.browser_24h, server_24h=stats.server_24h),
        setup=_setup_out(tenant),
        sync_error=sync_error,
    )


@router.get("/tenants/by-shop/{shop_domain}/markets", response_model=MarketsOut)
def list_markets(
    shop_domain: str,
    sync: bool = False,
    db: Session = Depends(get_db),
    markets: MarketService = Depends(get_market_service),
) -> MarketsOut:
    """The shop's Markets with their Market Pixels, 24 h counts and the setup
    flags. ``sync=true`` (app open) re-fetches them from Shopify first; if that
    fails the stored list is returned with ``sync_error`` set, so the page still
    renders."""
    tenant = _tenant_or_404(db, shop_domain)
    sync_error = None
    if sync:
        # App open also refreshes the storefront hosts, in the worker (spec §5).
        from app.models import AsyncJobOperation
        from app.services.async_job_service import AsyncJobService

        AsyncJobService(db).enqueue(
            tenant_id=tenant.id, operation=AsyncJobOperation.STOREFRONT_HOSTS_SYNC, topic="app_open/hosts"
        )
        try:
            return _markets_out(db, tenant, markets.sync(tenant))
        except Exception as exc:  # noqa: BLE001 — a failed re-fetch must not break the page
            db.rollback()
            sync_error = str(exc)[:500]
            logger.warn("markets.sync_on_open_failed", {"shop": shop_domain, "detail": sync_error})
    return _markets_out(db, tenant, markets.list_markets(tenant), sync_error)


@router.post("/tenants/by-shop/{shop_domain}/setup", response_model=SetupOut)
def update_setup(shop_domain: str, payload: SetupIn, db: Session = Depends(get_db)) -> SetupOut:
    """The setup-strip steps only the merchant can confirm (spec §4)."""
    from datetime import UTC, datetime

    tenant = _tenant_or_404(db, shop_domain)
    now = datetime.now(UTC)
    if payload.consent_confirmed is not None:
        tenant.consent_confirmed_at = now if payload.consent_confirmed else None
    if payload.verified_in_meta is not None:
        tenant.verified_in_meta_at = now if payload.verified_in_meta else None
    db.commit()
    return _setup_out(tenant)


@router.post("/relay", response_model=RelayOut)
def receive_relay(payload: RelayIn, db: Session = Depends(get_db)) -> RelayOut:
    """A Relay from the public /api/events endpoint on the BFF: decrypted,
    validated and stored here; the worker sends it (spec §3.2)."""
    from app.services.relay_service import RelayContext, RelayService

    outcome = RelayService(db).receive(
        payload.body, RelayContext(origin=payload.origin, ip=payload.ip, user_agent=payload.user_agent)
    )
    return RelayOut(outcome=outcome)


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


def _check_range(range_key: str) -> None:
    from app.services.event_stats import RANGES

    if range_key not in RANGES:
        raise HTTPException(status_code=422, detail=f"range must be one of {', '.join(RANGES)}")


@router.get("/tenants/by-shop/{shop_domain}/markets/{market_id}", response_model=MarketPageOut)
def market_page(
    shop_domain: str,
    market_id: int,
    range: str = "24h",  # noqa: A002 — the query parameter's name
    db: Session = Depends(get_db),
    markets: MarketService = Depends(get_market_service),
) -> MarketPageOut:
    """One Market for the Market page: its pixel, its 24 h tile figures (and held
    events of any age), and its figures for ``range`` (24h, 7d or 30d)."""
    from app.services.event_stats import market_detail

    tenant = _tenant_or_404(db, shop_domain)
    _check_range(range)
    view = next((m for m in markets.list_markets(tenant) if m.shopify_market_id == market_id), None)
    if view is None:
        raise HTTPException(status_code=404, detail=f"Market {market_id} isn't one of this shop's Markets")
    out = _markets_out(db, tenant, [view]).markets[0]
    return MarketPageOut(market=out, detail=MarketDetailOut.model_validate(asdict(market_detail(db, tenant, market_id, range))))


@router.get("/tenants/by-shop/{shop_domain}/markets/{market_id}/events", response_model=EventPageOut)
def market_events(
    shop_domain: str,
    market_id: int,
    range: str = "24h",  # noqa: A002 — the query parameter's name
    event: str | None = None,
    status: str | None = None,
    q: str | None = None,
    page: int = 1,
    db: Session = Depends(get_db),
) -> EventPageOut:
    """The Market page's event table: filter by event name and status (sent, held,
    waiting, rejected, failed, skipped), search by event ID or order number, 50 a page."""
    from app.services.event_stats import event_page

    tenant = _tenant_or_404(db, shop_domain)
    _check_range(range)
    result = event_page(
        db, tenant, market_id, range_key=range, event_name=event or None, status=status or None, search=q, page=page
    )
    return EventPageOut.model_validate(asdict(result))


@router.post("/tenants/by-shop/{shop_domain}/markets/{market_id}/pixel/recheck", response_model=PixelCheckOut)
def recheck_market_pixel(
    shop_domain: str,
    market_id: int,
    db: Session = Depends(get_db),
    markets: MarketService = Depends(get_market_service),
) -> PixelCheckOut:
    tenant = _tenant_or_404(db, shop_domain)
    try:
        check = markets.recheck(tenant, market_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PixelValidationError as exc:
        return PixelCheckOut(ok=False, error=str(exc))
    return PixelCheckOut(**asdict(check))


@router.post("/tenants/by-shop/{shop_domain}/markets/{market_id}/pixel/deactivate", response_model=MarketOut)
def deactivate_market_pixel(
    shop_domain: str,
    market_id: int,
    db: Session = Depends(get_db),
    markets: MarketService = Depends(get_market_service),
) -> MarketOut:
    """Stop the Market's events; the pixel ID and token stay saved."""
    tenant = _tenant_or_404(db, shop_domain)
    try:
        return _market_out(markets.deactivate(tenant, market_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/tenants/by-shop/{shop_domain}/markets/{market_id}/pixel/reactivate", response_model=MarketOut)
def reactivate_market_pixel(
    shop_domain: str,
    market_id: int,
    db: Session = Depends(get_db),
    markets: MarketService = Depends(get_market_service),
) -> MarketOut:
    tenant = _tenant_or_404(db, shop_domain)
    try:
        return _market_out(markets.reactivate(tenant, market_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
