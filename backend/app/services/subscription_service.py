"""The daily plan check (spec §5): re-read every installed shop's Partner API
``activeSubscription`` and reconcile it, so plan changes made outside the app — a
cancellation, a downgrade reaching the end of its cycle — take effect even if the
merchant never opens the app. Shops whose Shopify ID isn't known yet (never
opened the app) are skipped; a failed read leaves the shop as it was.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import BillingReconcileSource, Tenant, TenantStatus
from app.services.partner_billing_client import PartnerSubscriptionSnapshot

logger = get_logger().child({"component": "subscription"})


class SubscriptionSource(Protocol):
    configured: bool

    def fetch_active_subscription(self, shop_gid: str) -> PartnerSubscriptionSnapshot: ...


def check_all_subscriptions(db: Session, source: SubscriptionSource | None = None) -> dict[str, int]:
    from app.services.billing_reconcile_service import BillingReconcileService

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
            BillingReconcileService(db).reconcile(tenant.shop_domain, snapshot, BillingReconcileSource.SCHEDULED_WORKER)
        except Exception as exc:  # noqa: BLE001 — one shop must not stop the sweep
            db.rollback()
            failed += 1
            logger.warn("subscription.check_failed", {"shop": tenant.shop_domain, "detail": str(exc)[:300]})
            continue
        checked += 1
    logger.info("subscription.check_completed", {"checked": checked, "failed": failed})
    return {"checked": checked, "failed": failed}
