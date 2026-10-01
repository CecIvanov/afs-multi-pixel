"""Billing: plan catalog, entitlements + kill-switch, reconcile state machine
(incl. the trial-downgrade-immediate fix), and metered usage."""

from __future__ import annotations

import types
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.billing import entitlements
from app.billing.plan_catalog import classify_change, normalize_shopify_plan_name
from app.models import BillingReconcileSource, BillingSubscriptionEvent, TenantSubscription
from app.services.billing_reconcile_service import BillingReconcileService, ReconcileAction
from app.services.billing_service import BillingService, QuotaExceeded
from app.services.partner_billing_client import PartnerSubscriptionSnapshot
from app.services.tenant_service import TenantService

SHOP = "billing-shop.myshopify.com"


def _tenant(db):
    return TenantService(db).sync_shopify_install(SHOP, access_token="tok")


def _snapshot(**kw) -> PartnerSubscriptionSnapshot:
    base = dict(has_active_contract=True, effective_plan_handle="pro")
    base.update(kw)
    return PartnerSubscriptionSnapshot(**base)


# --- plan catalog (pure) ----------------------------------------------------
@pytest.mark.unit
def test_classify_change():
    assert classify_change("free", "pro") == "upgrade"
    assert classify_change("pro", "free") == "downgrade"
    assert classify_change("free", "free") == "same"


@pytest.mark.unit
def test_normalize_shopify_plan_name():
    assert normalize_shopify_plan_name("Pro") == "pro"
    assert normalize_shopify_plan_name("free") == "free"
    assert normalize_shopify_plan_name("MyApp Pro") == "pro"
    assert normalize_shopify_plan_name("nonsense") is None


# --- entitlements -----------------------------------------------------------
@pytest.mark.unit
def test_feature_gates_by_rank():
    assert entitlements.has_feature("pro", "example_premium_feature") is True
    assert entitlements.has_feature("free", "example_premium_feature") is False
    assert entitlements.has_feature("pro", "no_such_feature") is False


@pytest.mark.unit
def test_kill_switch_opens_all_gates(monkeypatch):
    monkeypatch.setattr(
        entitlements, "get_settings", lambda: types.SimpleNamespace(billing_enforcement_enabled=False)
    )
    # Enforcement off -> even a free tenant is treated as the top plan.
    assert entitlements.has_feature("free", "example_premium_feature") is True


# --- reconcile state machine ------------------------------------------------
@pytest.mark.integration
def test_reconcile_initial_selection(db):
    _tenant(db)
    result = BillingReconcileService(db).reconcile(SHOP, _snapshot(), BillingReconcileSource.APP_LOAD)
    assert result.action == ReconcileAction.INITIAL_SELECTION
    assert result.effective_plan_handle == "pro"
    # audit event written
    assert db.scalar(select(func.count()).select_from(BillingSubscriptionEvent)) == 1


@pytest.mark.integration
def test_reconcile_trial_downgrade_applies_immediately(db):
    """THE fix: a downgrade while on a free trial applies now, not at a cycle end
    that never comes."""
    tenant = _tenant(db)
    future = datetime.now(UTC) + timedelta(days=7)
    BillingService(db).apply_plan_change(tenant.id, "pro", trial_ends_at=future)

    result = BillingReconcileService(db).reconcile(
        SHOP, _snapshot(effective_plan_handle="pro", pending_plan_handle="free"), BillingReconcileSource.APP_LOAD
    )
    assert result.action == ReconcileAction.CANCELLED_TO_FREE
    assert result.effective_plan_handle == "free"  # applied immediately, not scheduled


@pytest.mark.integration
def test_reconcile_downgrade_scheduled_when_not_on_trial(db):
    tenant = _tenant(db)
    BillingService(db).apply_plan_change(tenant.id, "pro", trial_ends_at=None)

    result = BillingReconcileService(db).reconcile(
        SHOP, _snapshot(effective_plan_handle="pro", pending_plan_handle="free"), BillingReconcileSource.APP_LOAD
    )
    assert result.action == ReconcileAction.CANCEL_SCHEDULED
    assert result.effective_plan_handle == "pro"  # still on pro until cycle end
    assert result.pending_plan_handle == "free"


@pytest.mark.integration
def test_reconcile_no_contract_cancels_to_free(db):
    tenant = _tenant(db)
    BillingService(db).apply_plan_change(tenant.id, "pro", trial_ends_at=None)
    result = BillingReconcileService(db).reconcile(
        SHOP, PartnerSubscriptionSnapshot(has_active_contract=False), BillingReconcileSource.APP_LOAD
    )
    assert result.action == ReconcileAction.CANCELLED_TO_FREE
    assert result.effective_plan_handle == "free"


@pytest.mark.integration
def test_apply_pending_if_due_when_cycle_ended(db):
    tenant = _tenant(db)
    billing = BillingService(db)
    billing.apply_plan_change(tenant.id, "pro", trial_ends_at=None)
    billing.schedule_pending_plan(tenant.id, "free")
    # Force the cycle to have ended.
    sub = billing.get_subscription(tenant.id)
    sub.current_period_end = datetime.now(UTC) - timedelta(days=1)
    db.commit()

    assert billing.apply_pending_if_due(tenant.id) is True
    assert billing.current_plan_handle(tenant.id) == "free"


# --- metered usage ----------------------------------------------------------
@pytest.mark.integration
def test_usage_quota_guard(db):
    tenant = _tenant(db)  # free plan, quota 50
    billing = BillingService(db)
    for _ in range(50):
        assert billing.try_consume(tenant.id) is True
    assert billing.try_consume(tenant.id) is False  # 51st exceeds
    with pytest.raises(QuotaExceeded):
        billing.ensure_within_quota(tenant.id)
