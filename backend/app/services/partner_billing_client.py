"""Shopify Partner API `activeSubscription` snapshot.

Under managed pricing this — not the app_subscriptions/update webhook — is the
source of truth. The Node side fetches it on app load and passes it to the backend
reconcile endpoint; the scheduled worker fetches it here for drift reconciliation.

The fetch requires SHOPIFY_APP_GID + SHOPIFY_PARTNER_ORG_ID +
SHOPIFY_PARTNER_ACCESS_TOKEN and Partner API version 2026-07+; it is a thin,
network-only adapter (can't be unit-tested) — the reconcile STATE MACHINE takes a
snapshot, so its logic is fully testable without a network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class PartnerSubscriptionSnapshot:
    has_active_contract: bool
    effective_plan_handle: str | None = None
    pending_plan_handle: str | None = None
    billing_period: str | None = None  # "monthly" | "yearly"
    cancel_at_end_of_cycle: bool = False
    cycle_start: datetime | None = None
    cycle_end: datetime | None = None
    legacy_subscription_id: str | None = None
    trial_ends_at: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def as_audit(self) -> dict[str, Any]:
        return {
            "has_active_contract": self.has_active_contract,
            "effective_plan_handle": self.effective_plan_handle,
            "pending_plan_handle": self.pending_plan_handle,
            "billing_period": self.billing_period,
            "cancel_at_end_of_cycle": self.cancel_at_end_of_cycle,
            "trial_ends_at": self.trial_ends_at.isoformat() if self.trial_ends_at else None,
        }


class PartnerBillingClient:
    """Thin Partner API client for the scheduled reconcile worker. Returns None
    when unconfigured so the worker degrades gracefully."""

    def __init__(self) -> None:
        from app.config import get_settings

        s = get_settings()
        self.app_gid = getattr(s, "shopify_app_gid", None)
        self.org_id = getattr(s, "shopify_partner_org_id", None)
        self.access_token = getattr(s, "shopify_partner_access_token", None)

    @property
    def configured(self) -> bool:
        return bool(self.app_gid and self.org_id and self.access_token)

    def fetch_active_subscription(self, shop_domain: str) -> PartnerSubscriptionSnapshot | None:
        if not self.configured:
            return None
        # Implement the Partner API `app { events / subscriptions }` query here for
        # the scheduled worker. Left unimplemented in the template — the app-load
        # path (Node -> /internal/billing/reconcile) covers normal reconciliation.
        raise NotImplementedError("Partner API fetch not implemented in the template")
