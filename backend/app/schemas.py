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


class BillingReconcileOut(BaseModel):
    status: str
    action: str
    effective_plan_handle: str
    pending_plan_handle: str | None = None


class BillingOut(BaseModel):
    plan_handle: str
    plan_name: str
    pending_plan_handle: str | None = None
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
