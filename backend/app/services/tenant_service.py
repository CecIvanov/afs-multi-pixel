"""Tenant lifecycle: install (create / reactivate / refresh), session-sync, and
soft uninstall. The canonical `tenants` row is created here on install and its
Shopify credentials are kept fresh on every embedded navigation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.logging_config import get_logger
from app.models import BillingPlan, SubscriptionStatus, Tenant, TenantStatus, TenantSubscription
from app.reference_data import default_subscription_period

logger = get_logger().child({"component": "tenant"})

DEFAULT_APP_UI_LOCALE = "en"


def normalize_shop_domain(shop_domain: str) -> str:
    normalized = shop_domain.strip().lower()
    if normalized and not normalized.endswith(".myshopify.com"):
        normalized = f"{normalized}.myshopify.com"
    return normalized


class TenantService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- reads ---------------------------------------------------------------
    def get_tenant(self, tenant_id: uuid.UUID) -> Tenant | None:
        return self.db.get(Tenant, tenant_id)

    def get_tenant_by_shop_domain(self, shop_domain: str) -> Tenant | None:
        normalized = normalize_shop_domain(shop_domain)
        tenant = self.db.scalar(select(Tenant).where(Tenant.shop_domain == normalized))
        if tenant is None:
            tenant = self.db.scalar(
                select(Tenant).where(Tenant.shop_domain == shop_domain.strip().lower())
            )
        return tenant

    # --- install / create ----------------------------------------------------
    def create_tenant(
        self,
        shop_domain: str,
        *,
        access_token: str | None = None,
        scopes: str | None = None,
        refresh_token: str | None = None,
        access_token_expires_at: datetime | None = None,
        refresh_token_expires_at: datetime | None = None,
        plan_handle: str = "free",
    ) -> Tenant:
        existing = self.db.scalar(select(Tenant).where(Tenant.shop_domain == shop_domain))
        if existing:
            return existing

        tenant = Tenant(
            shop_domain=shop_domain,
            access_token=access_token,
            scopes=scopes,
            refresh_token=refresh_token,
            access_token_expires_at=access_token_expires_at,
            refresh_token_expires_at=refresh_token_expires_at,
            status=TenantStatus.ACTIVE,
            installed_at=datetime.now(UTC),
            app_ui_locale=DEFAULT_APP_UI_LOCALE,
        )
        self.db.add(tenant)
        self.db.flush()

        self._attach_default_subscription(tenant, plan_handle=plan_handle)
        self.db.commit()
        self.db.refresh(tenant)
        logger.info("tenant.created", {"tenantId": str(tenant.id), "shop": tenant.shop_domain})
        self._enqueue_shop_info_fetch(tenant)
        return tenant

    def _attach_default_subscription(self, tenant: Tenant, *, plan_handle: str) -> None:
        # billing_enforcement off -> put the tenant on the top plan so gates open.
        if not get_settings().billing_enforcement_enabled:
            plan_handle = get_app_top_plan_handle()
        plan = self.db.scalar(select(BillingPlan).where(BillingPlan.handle == plan_handle))
        if plan is None:  # plans not seeded yet — install still succeeds without one
            logger.warn("tenant.no_billing_plan", {"planHandle": plan_handle})
            return
        period_start, period_end = default_subscription_period()
        self.db.add(
            TenantSubscription(
                tenant_id=tenant.id,
                billing_plan_id=plan.id,
                status=(
                    SubscriptionStatus.ACTIVE
                    if not get_settings().billing_enforcement_enabled
                    else SubscriptionStatus.PENDING
                ),
                current_period_start=period_start,
                current_period_end=period_end,
            )
        )

    def sync_shopify_install(
        self,
        shop_domain: str,
        *,
        access_token: str,
        scopes: str | None = None,
        refresh_token: str | None = None,
        access_token_expires_at: datetime | None = None,
        refresh_token_expires_at: datetime | None = None,
    ) -> Tenant:
        normalized = normalize_shop_domain(shop_domain)
        tenant = self.get_tenant_by_shop_domain(shop_domain)

        if tenant is None:
            return self.create_tenant(
                normalized,
                access_token=access_token,
                scopes=scopes,
                refresh_token=refresh_token,
                access_token_expires_at=access_token_expires_at,
                refresh_token_expires_at=refresh_token_expires_at,
            )

        if tenant.status == TenantStatus.UNINSTALLED:
            # Reinstall: reactivate the existing row rather than inserting a new one.
            self._apply_credentials(
                tenant, access_token, scopes, refresh_token,
                access_token_expires_at, refresh_token_expires_at,
            )
            tenant.status = TenantStatus.ACTIVE
            tenant.installed_at = datetime.now(UTC)
            tenant.uninstalled_at = None
            self.db.commit()
            self.db.refresh(tenant)
            logger.info("tenant.reinstalled", {"tenantId": str(tenant.id), "shop": tenant.shop_domain})
            self._enqueue_shop_info_fetch(tenant)
            return tenant

        return self.sync_shopify_session(
            shop_domain,
            access_token=access_token,
            scopes=scopes,
            refresh_token=refresh_token,
            access_token_expires_at=access_token_expires_at,
            refresh_token_expires_at=refresh_token_expires_at,
            tenant=tenant,
        )

    def sync_shopify_session(
        self,
        shop_domain: str,
        *,
        access_token: str,
        scopes: str | None = None,
        refresh_token: str | None = None,
        access_token_expires_at: datetime | None = None,
        refresh_token_expires_at: datetime | None = None,
        tenant: Tenant | None = None,
    ) -> Tenant:
        """Refresh credentials for an active tenant without touching install timestamps."""
        tenant = tenant or self.get_tenant_by_shop_domain(shop_domain)
        if not tenant:
            raise ValueError(f"Tenant not found for shop '{shop_domain}'")
        if tenant.status == TenantStatus.UNINSTALLED:
            raise ValueError("Tenant is uninstalled; use install to reactivate")

        changed = self._apply_credentials(
            tenant, access_token, scopes, refresh_token,
            access_token_expires_at, refresh_token_expires_at,
        )
        self.db.commit()
        self.db.refresh(tenant)
        if changed:
            logger.info("tenant.session_synced", {"tenantId": str(tenant.id), "shop": tenant.shop_domain})
        return tenant

    def sync_shopify_uninstall(self, shop_domain: str) -> Tenant | None:
        tenant = self.get_tenant_by_shop_domain(shop_domain)
        if not tenant:
            logger.warn("tenant.uninstall_ignored", {"shop": shop_domain})
            return None
        # SOFT uninstall: keep the row + data, drop credentials, mark uninstalled.
        tenant.status = TenantStatus.UNINSTALLED
        tenant.uninstalled_at = datetime.now(UTC)
        tenant.access_token = None
        tenant.refresh_token = None
        tenant.access_token_expires_at = None
        tenant.refresh_token_expires_at = None
        tenant.shopify_refresh_token_revoked_at = None
        self.db.commit()
        self.db.refresh(tenant)
        logger.info("tenant.uninstalled", {"tenantId": str(tenant.id), "shop": tenant.shop_domain})
        return tenant

    # --- helpers -------------------------------------------------------------
    def _apply_credentials(
        self, tenant: Tenant, access_token: str, scopes: str | None,
        refresh_token: str | None, access_token_expires_at: datetime | None,
        refresh_token_expires_at: datetime | None,
    ) -> bool:
        before = (tenant.access_token, tenant.scopes, tenant.refresh_token)
        tenant.access_token = access_token
        if scopes is not None:
            tenant.scopes = scopes
        if refresh_token is not None:
            tenant.refresh_token = refresh_token
        if access_token_expires_at is not None:
            tenant.access_token_expires_at = access_token_expires_at
        if refresh_token_expires_at is not None:
            tenant.refresh_token_expires_at = refresh_token_expires_at
        tenant.shopify_refresh_token_revoked_at = None
        return before != (tenant.access_token, tenant.scopes, tenant.refresh_token)

    # --- token refresh (offline-token rotation) ------------------------------
    def apply_shopify_credentials(
        self,
        tenant: Tenant,
        credentials: "ShopifyTokenCredentials",
        *,
        reason: str,
        commit: bool = True,
    ) -> Tenant:
        """Persist a freshly-refreshed offline token onto the tenant AND mirror it
        into the Prisma Session row (rotating refresh tokens must stay in lockstep —
        see shopify_session_service). No-ops when nothing actually changed, clears
        any stale revoked flag when it did."""
        from app.services.shopify_session_service import ShopifySessionService
        from app.services.shopify_token_credentials import ShopifyTokenCredentials as _Creds

        previous = _Creds.from_tenant(tenant)
        if not credentials.metadata_changed(previous):
            return tenant

        tenant.access_token = credentials.access_token
        if credentials.scopes is not None:
            tenant.scopes = credentials.scopes
        if credentials.refresh_token is not None:
            tenant.refresh_token = credentials.refresh_token
        if credentials.access_token_expires_at is not None:
            tenant.access_token_expires_at = credentials.access_token_expires_at
        if credentials.refresh_token_expires_at is not None:
            tenant.refresh_token_expires_at = credentials.refresh_token_expires_at
        tenant.shopify_refresh_token_revoked_at = None

        ShopifySessionService(self.db).sync_offline_session_tokens(tenant.shop_domain, credentials)
        if commit:
            self.db.commit()
            self.db.refresh(tenant)
        logger.info(
            "tenant.credentials_applied",
            {
                "tenantId": str(tenant.id),
                "shop": tenant.shop_domain,
                "reason": reason,
                "tokenChanged": credentials.access_token != previous.access_token,
            },
        )
        return tenant

    def mark_refresh_token_revoked(
        self, tenant: Tenant, *, reason: str, detail: str | None = None
    ) -> Tenant:
        """Flag a dead offline refresh chain — the merchant must re-auth. Idempotent."""
        if tenant.shopify_refresh_token_revoked_at is not None:
            return tenant
        tenant.shopify_refresh_token_revoked_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(tenant)
        logger.warn(
            "tenant.refresh_token_revoked",
            {"tenantId": str(tenant.id), "shop": tenant.shop_domain, "reason": reason, "detail": detail},
        )
        return tenant

    def clear_refresh_token_revoked(self, tenant: Tenant, *, commit: bool = True) -> None:
        if tenant.shopify_refresh_token_revoked_at is None:
            return
        tenant.shopify_refresh_token_revoked_at = None
        if commit:
            self.db.commit()
            self.db.refresh(tenant)

    def _enqueue_shop_info_fetch(self, tenant: Tenant) -> None:
        """Best-effort async capture of the store profile via the durable job queue
        (a plain DB insert — needs no broker, so it never blocks install). The job
        pool processes it; a failure retries + dead-letters like any other job."""
        if not (tenant.access_token and tenant.status == TenantStatus.ACTIVE):
            return
        try:
            from app.services.async_job_service import AsyncJobService

            AsyncJobService(self.db).enqueue_shop_info_fetch(tenant.id)
        except Exception as exc:  # noqa: BLE001 — enqueue must never fail install
            logger.warn("tenant.shop_info_enqueue_failed", {"tenantId": str(tenant.id), "detail": str(exc)})


def get_app_top_plan_handle() -> str:
    from app.billing.plan_catalog import top_plan_handle

    return top_plan_handle()
