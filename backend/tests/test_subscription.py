"""Plan access (spec §1, §5): the Partner API activeSubscription is read on app open
(the BFF posts it to /billing/reconcile) and daily for every shop; any plan above
"none" gives access, and without one Relays stop."""

from __future__ import annotations

import json

import httpx
import pytest

from app.services.partner_billing_client import PartnerBillingClient, parse_active_subscription
from app.services.subscription_service import check_all_subscriptions
from tests.conftest import INTERNAL_HEADERS
from tests.test_markets import SHOP, _tenant
from tests.test_relay import _receive, _shop

ACTIVE = {
    "activeSubscription": {
        "billingPeriod": "MONTHLY",
        "cancelAtEndOfCycle": False,
        "trialEndsAt": None,
        "currentBillingCycle": {"startTime": "2026-10-01T00:00:00Z", "endTime": "2026-10-31T00:00:00Z"},
        "items": [{"handle": "light"}],
        "pendingUpdate": {"billingPeriod": "MONTHLY", "items": [{"handle": "shopify-test"}]},
    }
}


def _snapshot_json(**over):
    snap = {"has_active_contract": True, "effective_plan_handle": "light", "pending_plan_handle": None,
            "cycle_start": "2026-10-01T00:00:00Z", "cycle_end": "2026-10-31T00:00:00Z"}
    snap.update(over)
    return snap


# --- the Partner API -------------------------------------------------------------------
@pytest.mark.unit
def test_the_answer_carries_the_effective_and_pending_plan():
    snapshot = parse_active_subscription(ACTIVE)

    assert (snapshot.has_active_contract, snapshot.effective_plan_handle, snapshot.pending_plan_handle) == (
        True, "light", "shopify-test"
    )
    assert parse_active_subscription({"activeSubscription": None}).has_active_contract is False


@pytest.mark.unit
def test_the_client_sends_the_documented_partner_api_query(monkeypatch):
    from app.config import get_settings
    from app.services import partner_billing_client

    for key, value in {
        "shopify_app_gid": "gid://shopify/App/1",
        "shopify_partner_org_id": "123",
        "shopify_partner_access_token": "prtapi_x",
    }.items():
        monkeypatch.setattr(get_settings(), key, value)
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": ACTIVE})

    monkeypatch.setattr(partner_billing_client, "_transport", httpx.MockTransport(handler))

    snapshot = PartnerBillingClient().fetch_active_subscription("gid://shopify/Shop/77")

    assert snapshot.effective_plan_handle == "light"
    (request,) = seen
    assert str(request.url) == "https://partners.shopify.com/123/api/2026-07/graphql.json"
    assert request.headers["X-Shopify-Access-Token"] == "prtapi_x"
    body = json.loads(request.content)
    assert "activeSubscription(appId: $appId, shopId: $shopId)" in body["query"]
    assert body["variables"] == {"appId": "gid://shopify/App/1", "shopId": "gid://shopify/Shop/77"}


# --- app open: the BFF posts the snapshot ------------------------------------------------
@pytest.mark.integration
def test_app_open_reconciles_and_keeps_the_shop_id(db, client):
    tenant = _tenant(db)

    response = client.post(
        "/api/v1/internal/billing/reconcile",
        json={"shop_domain": SHOP, "partner_snapshot": _snapshot_json(effective_plan_handle="shopify-test"),
              "shop_gid": "gid://shopify/Shop/77"},
        headers=INTERNAL_HEADERS,
    )

    assert response.json()["subscribed"] is True
    assert response.json()["effective_plan_handle"] == "shopify-test"
    db.refresh(tenant)
    assert (tenant.subscription_active, tenant.shopify_shop_id) == (True, 77)


@pytest.mark.integration
def test_no_subscription_means_no_access(db, client):
    _tenant(db)

    response = client.post(
        "/api/v1/internal/billing/reconcile",
        json={"shop_domain": SHOP, "partner_snapshot": {"has_active_contract": False}},
        headers=INTERNAL_HEADERS,
    )

    assert response.json()["subscribed"] is False and response.json()["effective_plan_handle"] == "none"


# --- what it gates -----------------------------------------------------------------------
@pytest.mark.integration
def test_relays_stop_for_a_shop_without_a_plan(db):
    from app.models import BillingReconcileSource
    from app.services.billing_reconcile_service import BillingReconcileService

    _shop(db)
    BillingReconcileService(db).reconcile(SHOP, parse_active_subscription(ACTIVE), BillingReconcileSource.APP_LOAD)
    BillingReconcileService(db).reconcile(
        SHOP, parse_active_subscription({"activeSubscription": None}), BillingReconcileSource.APP_LOAD
    )

    assert _receive(db) == "rejected"


@pytest.mark.integration
def test_a_shop_never_checked_yet_still_sends(db):
    _shop(db)  # subscription_active is unknown (NULL) until the first reconcile

    assert _receive(db) == "stored"


@pytest.mark.integration
def test_the_daily_check_catches_a_cancellation_made_outside_the_app(db):
    from app.models import BillingReconcileSource
    from app.services.billing_reconcile_service import BillingReconcileService

    tenant = _tenant(db)
    tenant.shopify_shop_id = 77
    db.commit()
    BillingReconcileService(db).reconcile(SHOP, parse_active_subscription(ACTIVE), BillingReconcileSource.APP_LOAD)

    class CancelledEverywhere:
        configured = True

        def fetch_active_subscription(self, shop_gid):
            assert shop_gid == "gid://shopify/Shop/77"
            return parse_active_subscription({"activeSubscription": None})

    assert check_all_subscriptions(db, CancelledEverywhere()) == {"checked": 1, "failed": 0}
    db.refresh(tenant)
    assert tenant.subscription_active is False
