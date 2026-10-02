"""The one paid plan (spec §1, §5): Shopify App Pricing (managed pricing). The app
knows only the plan's exact handle ("light") and reads the shop's subscription
from the Partner API ``activeSubscription``; without it, Relays stop."""

from __future__ import annotations

import httpx
import pytest

from app.services.partner_billing_client import PartnerBillingClient, parse_active_subscription
from app.services.subscription_service import (
    check_all_subscriptions,
    is_subscribed,
    plan_handle,
    set_subscription_active,
)
from tests.test_markets import SHOP, _tenant
from tests.test_relay import _receive, _shop

ACTIVE = {
    "activeSubscription": {
        "billingPeriod": "MONTHLY",
        "cancelAtEndOfCycle": False,
        "trialEndsAt": None,
        "currentBillingCycle": {"startTime": "2026-10-01T00:00:00Z", "endTime": "2026-10-31T00:00:00Z"},
        "items": [{"handle": "light"}],
        "pendingUpdate": None,
    }
}


# --- reading the Partner API answer ------------------------------------------------------
@pytest.mark.unit
def test_an_active_subscription_to_the_plan_handle_counts():
    assert plan_handle() == "light"
    assert is_subscribed(parse_active_subscription(ACTIVE)) is True


@pytest.mark.unit
def test_no_contract_or_another_plan_doesnt_count():
    assert is_subscribed(parse_active_subscription({"activeSubscription": None})) is False
    other = {"activeSubscription": {**ACTIVE["activeSubscription"], "items": [{"handle": "pro"}]}}
    assert is_subscribed(parse_active_subscription(other)) is False


@pytest.mark.unit
def test_a_cancellation_at_the_end_of_the_cycle_still_counts_until_then():
    cancelling = {"activeSubscription": {**ACTIVE["activeSubscription"], "cancelAtEndOfCycle": True}}
    snapshot = parse_active_subscription(cancelling)
    assert snapshot.cancel_at_end_of_cycle is True and is_subscribed(snapshot) is True


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
    body = __import__("json").loads(request.content)
    assert "activeSubscription(appId: $appId, shopId: $shopId)" in body["query"]
    assert body["variables"] == {"appId": "gid://shopify/App/1", "shopId": "gid://shopify/Shop/77"}


# --- what it gates ------------------------------------------------------------------------
@pytest.mark.integration
def test_relays_stop_for_a_shop_without_the_subscription(db):
    tenant = _shop(db)

    set_subscription_active(db, tenant, False)

    assert _receive(db) == "rejected"


@pytest.mark.integration
def test_a_shop_never_checked_yet_still_sends(db):
    _shop(db)  # subscription_active is unknown (NULL) until the first check

    assert _receive(db) == "stored"


@pytest.mark.integration
def test_the_bff_reports_the_subscription_and_the_shop_id(db, client):
    from tests.conftest import INTERNAL_HEADERS

    tenant = _tenant(db)

    response = client.post(
        f"/api/v1/internal/tenants/by-shop/{SHOP}/subscription",
        json={"active": True, "shop_gid": "gid://shopify/Shop/77"},
        headers=INTERNAL_HEADERS,
    )

    assert response.status_code == 200
    db.refresh(tenant)
    assert (tenant.subscription_active, tenant.shopify_shop_id) == (True, 77)


@pytest.mark.integration
def test_the_daily_check_catches_a_cancellation_made_outside_the_app(db):
    tenant = _tenant(db)
    tenant.shopify_shop_id = 77
    set_subscription_active(db, tenant, True)

    class CancelledEverywhere:
        configured = True

        def fetch_active_subscription(self, shop_gid):
            assert shop_gid == "gid://shopify/Shop/77"
            return parse_active_subscription({"activeSubscription": None})

    assert check_all_subscriptions(db, CancelledEverywhere()) == {"checked": 1, "failed": 0}
    db.refresh(tenant)
    assert tenant.subscription_active is False
