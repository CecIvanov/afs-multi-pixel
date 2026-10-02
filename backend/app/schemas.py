from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BillingPlan, Tenant, TenantStatus, TenantSubscription


class WebhookIngestIn(BaseModel):
    shop_domain: str
    topic: str
    shopify_webhook_id: str | None = None
    payload: dict[str, Any] | None = None
    webhook_context: dict[str, Any] | None = None


class WebhookIngestOut(BaseModel):
    status: str
    duplicate: bool = False
    job_id: uuid.UUID | None = None
    webhook_event_id: uuid.UUID | None = None


class PartnerSnapshotIn(BaseModel):
    has_active_contract: bool
    effective_plan_handle: str | None = None
    pending_plan_handle: str | None = None
    billing_period: str | None = None
    cancel_at_end_of_cycle: bool = False
    cycle_start: datetime | None = None
    cycle_end: datetime | None = None
    legacy_subscription_id: str | None = None
    trial_ends_at: datetime | None = None


class BillingReconcileIn(BaseModel):
    shop_domain: str
    source: str = "app_load"
    partner_snapshot: PartnerSnapshotIn
    # gid://shopify/Shop/<id>, kept so the daily check can ask the Partner API.
    shop_gid: str | None = None


class BillingReconcileOut(BaseModel):
    status: str
    action: str
    effective_plan_handle: str
    pending_plan_handle: str | None = None
    # Any plan above the catalog's "none" gives access.
    subscribed: bool = False


class BillingOut(BaseModel):
    plan_handle: str
    plan_name: str
    pending_plan_handle: str | None = None
    pending_plan_name: str | None = None
    # When the pending (lower) plan takes over: the end of the current cycle.
    current_period_end: datetime | None = None
    subscribed: bool = False
    status: str
    used: int = 0
    quota: int | None = None
    supports: dict[str, bool] = Field(default_factory=dict)


class ShopifyInstallIn(BaseModel):
    shop_domain: str
    access_token: str
    scopes: str | None = None
    refresh_token: str | None = None
    access_token_expires_at: datetime | None = None
    refresh_token_expires_at: datetime | None = None


class ShopifySessionSyncIn(BaseModel):
    shop_domain: str
    access_token: str
    scopes: str | None = None
    refresh_token: str | None = None
    access_token_expires_at: datetime | None = None
    refresh_token_expires_at: datetime | None = None


class ShopifyUninstallIn(BaseModel):
    shop_domain: str


class TenantOut(BaseModel):
    id: uuid.UUID
    shop_domain: str
    status: TenantStatus
    created_at: datetime
    installed_at: datetime | None = None
    app_ui_locale: str = "en"
    plan_handle: str | None = None
    feature_flags: dict[str, bool] = Field(default_factory=dict)


def tenant_to_out(tenant: Tenant, db: Session) -> TenantOut:
    plan_handle: str | None = None
    subscription = db.scalar(
        select(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id)
    )
    if subscription is not None:
        plan = db.get(BillingPlan, subscription.billing_plan_id)
        plan_handle = plan.handle if plan else None
    return TenantOut(
        id=tenant.id,
        shop_domain=tenant.shop_domain,
        status=tenant.status,
        created_at=tenant.created_at,
        installed_at=tenant.installed_at,
        app_ui_locale=tenant.app_ui_locale,
        plan_handle=plan_handle,
        feature_flags=tenant.feature_flags or {},
    )


# --- Markets and the Pixel Mapping ------------------------------------------------
class PixelOut(BaseModel):
    pixel_id: str
    pixel_name: str | None = None
    test_event_code: str | None = None
    token_state: str
    has_token: bool
    token_error: str | None = None


class MarketStatsOut(BaseModel):
    browser: int = 0
    server: int = 0
    purchases: int = 0
    series: list[int] = Field(default_factory=lambda: [0] * 24)
    last_event_at: datetime | None = None
    held: int = 0
    held_until: datetime | None = None


class MarketOut(BaseModel):
    shopify_market_id: int
    name: str
    market_type: str
    status: str
    regions: list[str] = Field(default_factory=list)
    first_seen_at: datetime
    is_new: bool
    pixel: PixelOut | None = None
    stats: MarketStatsOut = Field(default_factory=MarketStatsOut)


class SummaryOut(BaseModel):
    browser_24h: int = 0
    server_24h: int = 0


class SetupOut(BaseModel):
    consent_confirmed: bool = False
    verified_in_meta: bool = False


class SetupIn(BaseModel):
    consent_confirmed: bool | None = None
    verified_in_meta: bool | None = None


class MarketsOut(BaseModel):
    markets: list[MarketOut]
    summary: SummaryOut = Field(default_factory=SummaryOut)
    setup: SetupOut = Field(default_factory=SetupOut)
    # Set when the re-fetch from Shopify failed and the stored list is shown instead.
    sync_error: str | None = None


class PixelCheckIn(BaseModel):
    pixel_id: str
    # Blank means "use the token already saved for this Market".
    token: str | None = None


class PixelSaveIn(PixelCheckIn):
    test_event_code: str | None = None


class PixelCheckOut(BaseModel):
    ok: bool
    pixel_name: str | None = None
    error: str | None = None


class RelayIn(BaseModel):
    """A Relay as the BFF received it: the raw envelope and the request facts."""

    body: str = Field(max_length=64 * 1024)
    origin: str | None = None
    ip: str | None = None
    user_agent: str | None = None


class RelayOut(BaseModel):
    outcome: str


class EventLogRowOut(BaseModel):
    created_at: datetime
    event_name: str
    event_id: str
    shopify_market_id: int
    sent_as: str
    status: str
    detail: str | None = None


class EventLogOut(BaseModel):
    events: list[EventLogRowOut]
