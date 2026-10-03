"""Billing (spec §1, §5): Shopify App Pricing plans from app.config.json, ordered by
rank — "none" (not subscribed) < "shopify-test" (free; Shopify's review plan) <
"light". The reconcile state machine mirrors Shopify's standard plan changes: an
upgrade applies at once; a downgrade stays pending until the cycle ends while the
higher plan stays effective; once Shopify switches, the lower plan is effective.
Any plan above "none" gives access."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.billing.plan_catalog import classify_change, free_plan_handle, get_plans
from app.models import BillingReconcileSource, BillingSubscriptionEvent, Tenant
from app.services.billing_reconcile_service import BillingReconcileService, ReconcileAction
from app.services.billing_service import BillingService
from app.services.partner_billing_client import PartnerSubscriptionSnapshot
from app.services.tenant_service import TenantService

SHOP = "billing-shop.myshopify.com"
CYCLE_START = datetime(2026, 10, 1, tzinfo=UTC)
CYCLE_END = datetime(2026, 10, 31, tzinfo=UTC)


def _tenant(db) -> Tenant:
    return TenantService(db).sync_shopify_install(SHOP, access_token="tok")


def _snapshot(effective: str | None = "light", pending: str | None = None, **kw) -> PartnerSubscriptionSnapshot:
    base = dict(
        has_active_contract=effective is not None,
        effective_plan_handle=effective,
        pending_plan_handle=pending,
        cycle_start=CYCLE_START,
        cycle_end=CYCLE_END,
    )
    base.update(kw)
    return PartnerSubscriptionSnapshot(**base)


def _reconcile(db, snapshot):
    return BillingReconcileService(db).reconcile(SHOP, snapshot, BillingReconcileSource.APP_LOAD)


def _subscribed(db, tenant) -> bool | None:
    db.refresh(tenant)
    return tenant.subscription_active


# --- the catalog ---------------------------------------------------------------------
@pytest.mark.unit
def test_the_catalog_ranks_none_then_shopify_test_then_light():
    assert [p.handle for p in get_plans()] == ["none", "shopify-test", "light"]
    assert free_plan_handle() == "none"
    assert classify_change("shopify-test", "light") == "upgrade"
    assert classify_change("light", "shopify-test") == "downgrade"
    assert classify_change("none", "shopify-test") == "upgrade"


@pytest.mark.integration
def test_a_new_install_has_no_plan(db):
    tenant = _tenant(db)

    assert BillingService(db).current_plan_handle(tenant.id) == "none"


# --- the standard Shopify plan changes ------------------------------------------------
@pytest.mark.integration
def test_choosing_shopify_test_at_install_gives_access(db):
    tenant = _tenant(db)

    result = _reconcile(db, _snapshot("shopify-test"))

    assert result.action == ReconcileAction.INITIAL_SELECTION
    assert result.effective_plan_handle == "shopify-test"
    assert _subscribed(db, tenant) is True
    assert db.scalar(select(func.count()).select_from(BillingSubscriptionEvent)) == 1


@pytest.mark.integration
def test_shopify_test_to_light_is_an_upgrade_effective_at_once(db):
    _tenant(db)
    _reconcile(db, _snapshot("shopify-test"))

    result = _reconcile(db, _snapshot("light"))

    assert result.action == ReconcileAction.UPGRADE_APPLIED
    assert (result.effective_plan_handle, result.pending_plan_handle) == ("light", None)


@pytest.mark.integration
def test_light_to_shopify_test_waits_for_the_end_of_the_cycle(db):
    tenant = _tenant(db)
    _reconcile(db, _snapshot("shopify-test"))
    _reconcile(db, _snapshot("light"))

    # Shopify keeps light until the cycle ends and reports shopify-test as pending.
    result = _reconcile(db, _snapshot("light", pending="shopify-test"))

    assert result.action == ReconcileAction.DOWNGRADE_SCHEDULED
    assert (result.effective_plan_handle, result.pending_plan_handle) == ("light", "shopify-test")
    assert _subscribed(db, tenant) is True
    # Seeing the same pending change again changes nothing.
    assert _reconcile(db, _snapshot("light", pending="shopify-test")).action == ReconcileAction.UNCHANGED


@pytest.mark.integration
def test_at_the_end_of_the_cycle_the_pending_plan_becomes_effective(db):
    _tenant(db)
    _reconcile(db, _snapshot("light"))
    _reconcile(db, _snapshot("light", pending="shopify-test"))

    # The cycle ended: Shopify now reports shopify-test as the effective plan.
    next_cycle = dict(cycle_start=CYCLE_END, cycle_end=CYCLE_END + timedelta(days=30))
    result = _reconcile(db, _snapshot("shopify-test", **next_cycle))

    assert result.action == ReconcileAction.DOWNGRADE_EFFECTIVE
    assert (result.effective_plan_handle, result.pending_plan_handle) == ("shopify-test", None)
    assert _reconcile(db, _snapshot("shopify-test", **next_cycle)).action == ReconcileAction.UNCHANGED


@pytest.mark.integration
def test_a_scheduled_downgrade_applies_once_our_recorded_cycle_has_ended(db):
    tenant = _tenant(db)
    billing = BillingService(db)
    _reconcile(db, _snapshot("light"))
    _reconcile(db, _snapshot("light", pending="shopify-test"))
    sub = billing.get_subscription(tenant.id)
    sub.current_period_end = datetime.now(UTC) - timedelta(days=1)
    db.commit()

    assert billing.apply_pending_if_due(tenant.id) is True
    assert billing.current_plan_handle(tenant.id) == "shopify-test"


@pytest.mark.integration
def test_cancelling_the_subscription_removes_access(db):
    tenant = _tenant(db)
    _reconcile(db, _snapshot("light"))

    result = _reconcile(db, _snapshot(None))

    assert result.effective_plan_handle == "none"
    assert _subscribed(db, tenant) is False


@pytest.mark.integration
def test_a_renewal_moves_the_cycle_forward(db):
    tenant = _tenant(db)
    _reconcile(db, _snapshot("light"))

    result = _reconcile(db, _snapshot("light", cycle_start=CYCLE_END, cycle_end=CYCLE_END + timedelta(days=30)))

    assert result.action == ReconcileAction.SUBSCRIPTION_RENEWED
    assert BillingService(db).get_subscription(tenant.id).current_period_end == CYCLE_END + timedelta(days=30)


@pytest.mark.integration
def test_a_plan_shopify_reports_that_the_catalog_doesnt_know_changes_nothing(db):
    tenant = _tenant(db)
    _reconcile(db, _snapshot("light"))

    result = _reconcile(db, _snapshot("enterprise"))

    assert result.action == ReconcileAction.UNCHANGED
    assert BillingService(db).current_plan_handle(tenant.id) == "light"


@pytest.mark.integration
def test_a_downgrade_during_a_trial_applies_at_once(db):
    """No paid cycle to wait for (spec: no trial today, but plans may get one)."""
    tenant = _tenant(db)
    BillingService(db).apply_plan_change(tenant.id, "light", trial_ends_at=datetime.now(UTC) + timedelta(days=7))

    result = _reconcile(db, _snapshot("light", pending="shopify-test"))

    assert result.action == ReconcileAction.DOWNGRADE_EFFECTIVE
    assert result.effective_plan_handle == "shopify-test"


@pytest.mark.integration
def test_a_future_higher_plan_follows_the_same_rules(db, monkeypatch):
    from app.billing import plan_catalog
    from app.services.plan_catalog_sync import sync_plan_catalog

    plans = (*get_plans(), plan_catalog.PlanSpec("pro", "Pro", 30, "pro", None, ()))
    monkeypatch.setattr(plan_catalog, "get_plans", lambda: plans)
    sync_plan_catalog(db)
    _tenant(db)
    _reconcile(db, _snapshot("light"))

    assert _reconcile(db, _snapshot("pro")).action == ReconcileAction.UPGRADE_APPLIED
    scheduled = _reconcile(db, _snapshot("pro", pending="light"))
    assert (scheduled.effective_plan_handle, scheduled.pending_plan_handle) == ("pro", "light")


# --- Shopify's redirect after the merchant picks a plan --------------------------------
def _no_contract() -> PartnerSubscriptionSnapshot:
    return PartnerSubscriptionSnapshot(has_active_contract=False)


def _redirect(db, handle):
    return BillingReconcileService(db).reconcile(
        SHOP, _no_contract(), BillingReconcileSource.APP_LOAD, redirect_plan_handle=handle
    )


@pytest.mark.integration
def test_the_plan_in_shopifys_redirect_is_stored_before_the_partner_api_shows_it(db):
    tenant = _tenant(db)

    result = _redirect(db, "light")

    assert (result.action, result.effective_plan_handle) == (ReconcileAction.INITIAL_SELECTION, "light")
    assert _subscribed(db, tenant) is True
    event = db.scalars(select(BillingSubscriptionEvent)).one()
    assert event.source == BillingReconcileSource.REDIRECT


@pytest.mark.integration
def test_the_next_app_open_keeps_the_redirected_plan_while_the_partner_api_catches_up(db):
    tenant = _tenant(db)
    _redirect(db, "light")

    assert _reconcile(db, _no_contract()).effective_plan_handle == "light"
    assert _subscribed(db, tenant) is True


@pytest.mark.integration
def test_after_the_grace_period_the_partner_api_decides_again(db):
    tenant = _tenant(db)
    _redirect(db, "light")
    event = db.scalars(select(BillingSubscriptionEvent)).one()
    event.created_at = datetime.now(UTC) - timedelta(hours=1)
    db.commit()

    assert _reconcile(db, _no_contract()).effective_plan_handle == "none"
    assert _subscribed(db, tenant) is False


@pytest.mark.integration
def test_a_redirect_naming_no_plan_or_an_unknown_plan_gives_no_access(db):
    tenant = _tenant(db)

    assert _redirect(db, "none").effective_plan_handle == "none"
    assert _redirect(db, "enterprise").effective_plan_handle == "none"
    assert _subscribed(db, tenant) is False


@pytest.mark.integration
def test_the_partner_api_wins_over_the_redirect_when_it_already_shows_the_plan(db):
    _tenant(db)

    result = BillingReconcileService(db).reconcile(
        SHOP, _snapshot("shopify-test"), BillingReconcileSource.REDIRECT, redirect_plan_handle="light"
    )

    assert result.effective_plan_handle == "shopify-test"
