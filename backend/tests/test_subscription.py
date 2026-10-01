"""The one paid plan (spec §1, §5): the app knows only the plan's exact name and
whether the shop's subscription to it is active. Without one, Relays stop."""

from __future__ import annotations

import pytest

from app.services.subscription_service import is_plan_subscription_active, plan_name, set_subscription_active
from tests.test_markets import SHOP
from tests.test_relay import _receive, _shop


@pytest.mark.unit
def test_only_an_active_subscription_to_the_exact_plan_counts():
    plan = plan_name()
    assert is_plan_subscription_active({"name": plan, "status": "ACTIVE"}) is True
    assert is_plan_subscription_active({"name": plan, "status": "active"}) is True
    assert is_plan_subscription_active({"name": plan, "status": "CANCELLED"}) is False
    assert is_plan_subscription_active({"name": "Some other plan", "status": "ACTIVE"}) is False
    assert is_plan_subscription_active({}) is False


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
def test_the_subscription_webhook_updates_the_flag_through_the_inbox(db):
    from app.services.async_job_service import AsyncJobService
    from app.services.webhook_ingest_service import WebhookIngestService

    tenant = _shop(db)
    db.query(__import__("app.models", fromlist=["AsyncJob"]).AsyncJob).delete()
    db.commit()

    WebhookIngestService(db).ingest(
        shop_domain=SHOP,
        topic="app_subscriptions/update",
        shopify_webhook_id="sub-1",
        payload={"app_subscription": {"name": plan_name(), "status": "CANCELLED"}},
    )
    svc = AsyncJobService(db)
    while (job := svc.claim_next("w")) is not None:
        svc.process_job(job.id)

    db.refresh(tenant)
    assert tenant.subscription_active is False


@pytest.mark.integration
def test_the_bff_reports_the_subscription(db, client):
    from tests.conftest import INTERNAL_HEADERS
    from tests.test_markets import _tenant

    tenant = _tenant(db)

    response = client.post(f"/api/v1/internal/tenants/by-shop/{SHOP}/subscription", json={"active": True},
                           headers=INTERNAL_HEADERS)

    assert response.status_code == 200
    db.refresh(tenant)
    assert tenant.subscription_active is True
