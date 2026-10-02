"""Shopify Partner API `activeSubscription` snapshot (Shopify App Pricing).

Under managed pricing this is the source of truth: Shopify stopped sending
subscription webhooks for managed pricing after April 28, 2026. The Node side
reads it on app load (with the plan_handle redirect hint); the daily worker reads
it here so a cancellation made outside the app stops Relays.

Needs SHOPIFY_APP_GID + SHOPIFY_PARTNER_ORG_ID (in .env.<stack>) and
SHOPIFY_PARTNER_ACCESS_TOKEN (in .credentials.<stack>); Partner API 2026-07+.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx


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


ACTIVE_SUBSCRIPTION_QUERY = """
query ActiveSubscription($appId: ID!, $shopId: ID!) {
  activeSubscription(appId: $appId, shopId: $shopId) {
    billingPeriod
    cancelAtEndOfCycle
    trialEndsAt
    currentBillingCycle { startTime endTime }
    items { handle }
    pendingUpdate { billingPeriod items { handle } }
  }
}
"""

# Replaced in tests with an httpx.MockTransport.
_transport: httpx.BaseTransport | None = None


def _datetime(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


def _first_handle(items: Any) -> str | None:
    for item in items or []:
        handle = str((item or {}).get("handle") or "").strip().lower()
        if handle:
            return handle
    return None


def parse_active_subscription(data: dict[str, Any]) -> PartnerSubscriptionSnapshot:
    """The ``data`` of the activeSubscription query as a snapshot; null means the
    shop has no subscription to the app."""
    sub = data.get("activeSubscription")
    if not sub:
        return PartnerSubscriptionSnapshot(has_active_contract=False, raw=data)
    period = str(sub.get("billingPeriod") or "").upper()
    cycle = sub.get("currentBillingCycle") or {}
    return PartnerSubscriptionSnapshot(
        has_active_contract=True,
        effective_plan_handle=_first_handle(sub.get("items")),
        pending_plan_handle=_first_handle((sub.get("pendingUpdate") or {}).get("items")),
        billing_period="yearly" if period in ("ANNUAL", "YEARLY") else "monthly" if period else None,
        cancel_at_end_of_cycle=sub.get("cancelAtEndOfCycle") is True,
        cycle_start=_datetime(cycle.get("startTime")),
        cycle_end=_datetime(cycle.get("endTime")),
        trial_ends_at=_datetime(sub.get("trialEndsAt")),
        raw=data,
    )


class PartnerBillingClient:
    """Partner API client for the daily subscription check."""

    def __init__(self) -> None:
        from app.config import get_settings

        s = get_settings()
        self.app_gid = s.shopify_app_gid
        self.org_id = s.shopify_partner_org_id
        self.access_token = s.shopify_partner_access_token
        self.api_version = s.shopify_partner_api_version

    @property
    def configured(self) -> bool:
        return bool(self.app_gid and self.org_id and self.access_token)

    def fetch_active_subscription(self, shop_gid: str) -> PartnerSubscriptionSnapshot:
        """``shop_gid`` is ``gid://shopify/Shop/<id>``. Raises on any API error."""
        if not self.configured:
            raise RuntimeError("The Partner API isn't configured")
        url = f"https://partners.shopify.com/{self.org_id}/api/{self.api_version}/graphql.json"
        with httpx.Client(transport=_transport, timeout=20.0) as client:
            response = client.post(
                url,
                json={"query": ACTIVE_SUBSCRIPTION_QUERY, "variables": {"appId": self.app_gid, "shopId": shop_gid}},
                headers={"X-Shopify-Access-Token": str(self.access_token), "Content-Type": "application/json"},
            )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise RuntimeError("; ".join(str(e.get("message") or e) for e in payload["errors"]))
        return parse_active_subscription(payload.get("data") or {})
