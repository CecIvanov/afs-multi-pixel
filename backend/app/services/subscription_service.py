"""The one paid plan (spec §1, §5), billed by Shopify App Pricing. The app knows
only the plan's exact handle (BILLING_PLAN_HANDLE, "light") and whether the shop's
Partner API ``activeSubscription`` is to that plan; never an amount. A shop known
to have no active subscription gets no Relays accepted; NULL means "not checked
yet" and passes. The BFF checks on app open; ``check_all_subscriptions`` runs daily
so a cancellation made outside the app is caught.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.logging_config import get_logger
from app.models import Tenant, TenantStatus
from app.services.partner_billing_client import PartnerSubscriptionSnapshot

logger = get_logger().child({"component": "subscription"})


def plan_handle() -> str:
    return get_settings().billing_plan_handle.strip().lower()


def is_subscribed(snapshot: PartnerSubscriptionSnapshot) -> bool:
    """An active contract on the plan handle. A cancellation scheduled for the end
    of the cycle still counts until Shopify ends the contract."""
    return snapshot.has_active_contract and snapshot.effective_plan_handle == plan_handle()


def set_subscription_active(db: Session, tenant: Tenant, active: bool) -> None:
    if tenant.subscription_active != active:
        logger.info("subscription.changed", {"tenantId": str(tenant.id), "active": active})
    tenant.subscription_active = active
    db.commit()


class SubscriptionSource(Protocol):
    configured: bool

    def fetch_active_subscription(self, shop_gid: str) -> PartnerSubscriptionSnapshot: ...


def check_all_subscriptions(db: Session, source: SubscriptionSource | None = None) -> dict[str, int]:
    """Daily: re-read every installed shop's subscription. Shops whose Shopify ID
    isn't known yet (never opened the app) are skipped; a failed read leaves the
    flag as it was."""
    if source is None:
        from app.services.partner_billing_client import PartnerBillingClient

        source = PartnerBillingClient()
    if not source.configured:
        logger.info("subscription.check_skipped", {"reason": "partner_api_unconfigured"})
        return {"checked": 0, "failed": 0}
    checked = failed = 0
    tenants = db.scalars(
        select(Tenant).where(Tenant.status == TenantStatus.ACTIVE, Tenant.shopify_shop_id.is_not(None))
    ).all()
    for tenant in tenants:
        try:
            snapshot = source.fetch_active_subscription(f"gid://shopify/Shop/{tenant.shopify_shop_id}")
        except Exception as exc:  # noqa: BLE001 — one shop must not stop the sweep
            failed += 1
            logger.warn("subscription.check_failed", {"shop": tenant.shop_domain, "detail": str(exc)[:300]})
            continue
        set_subscription_active(db, tenant, is_subscribed(snapshot))
        checked += 1
    logger.info("subscription.check_completed", {"checked": checked, "failed": failed})
    return {"checked": checked, "failed": failed}
