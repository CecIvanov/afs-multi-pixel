"""Billing reconcile state machine.

Maps a Partner-API `activeSubscription` snapshot onto the tenant's subscription,
emits an action, and writes an audit event. Upgrades apply immediately (+ reset
usage); downgrades defer to cycle end via a pending plan — UNLESS the plan is
still inside its Shopify free trial, in which case the downgrade applies
immediately (there is no paid cycle to defer to — the bug this fixes gave the
merchant a free stretch of the higher tier for ~30 days).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.plan_catalog import classify_change, free_plan_handle, plan_by_handle
from app.logging_config import get_logger
from app.models import (
    BillingReconcileSource,
    BillingSubscriptionEvent,
    BillingSubscriptionEventType,
    Tenant,
    TenantSubscription,
)
from app.services.billing_service import BillingService
from app.services.partner_billing_client import PartnerSubscriptionSnapshot
from app.services.tenant_service import TenantService

logger = get_logger().child({"component": "billing_reconcile"})


class ReconcileAction(str, Enum):
    UNCHANGED = "unchanged"
    INITIAL_SELECTION = "initial_selection"
    UPGRADE_APPLIED = "upgrade_applied"
    DOWNGRADE_SCHEDULED = "downgrade_scheduled"
    DOWNGRADE_EFFECTIVE = "downgrade_effective"
    CANCEL_SCHEDULED = "cancel_scheduled"
    CANCELLED_TO_FREE = "cancelled_to_free"
    SUBSCRIPTION_RENEWED = "subscription_renewed"


_ACTION_TO_EVENT = {
    ReconcileAction.INITIAL_SELECTION: BillingSubscriptionEventType.INITIAL_SELECTION,
    ReconcileAction.UPGRADE_APPLIED: BillingSubscriptionEventType.UPGRADE,
    ReconcileAction.DOWNGRADE_SCHEDULED: BillingSubscriptionEventType.DOWNGRADE_SCHEDULED,
    ReconcileAction.DOWNGRADE_EFFECTIVE: BillingSubscriptionEventType.DOWNGRADE_EFFECTIVE,
    ReconcileAction.CANCEL_SCHEDULED: BillingSubscriptionEventType.CANCEL_SCHEDULED,
    ReconcileAction.CANCELLED_TO_FREE: BillingSubscriptionEventType.CANCELLED_TO_FREE,
    ReconcileAction.SUBSCRIPTION_RENEWED: BillingSubscriptionEventType.SUBSCRIPTION_RENEWED,
}


@dataclass(frozen=True)
class ReconcileResult:
    action: ReconcileAction
    effective_plan_handle: str
    pending_plan_handle: str | None


class BillingReconcileService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.billing = BillingService(db)

    @staticmethod
    def _on_trial(sub: TenantSubscription | None) -> bool:
        if not sub or sub.trial_ends_at is None:
            return False
        ends = sub.trial_ends_at
        if ends.tzinfo is None:
            ends = ends.replace(tzinfo=UTC)
        return datetime.now(UTC) < ends

    def _pending_handle(self, sub: TenantSubscription | None) -> str | None:
        if not sub or sub.pending_billing_plan_id is None:
            return None
        from app.models import BillingPlan

        plan = self.db.get(BillingPlan, sub.pending_billing_plan_id)
        return plan.handle if plan else None

    def reconcile(
        self, shop_domain: str, snapshot: PartnerSubscriptionSnapshot, source: BillingReconcileSource
    ) -> ReconcileResult:
        tenant = TenantService(self.db).get_tenant_by_shop_domain(shop_domain)
        if not tenant:
            raise ValueError("Tenant not found")

        sub = self.billing.get_subscription(tenant.id)
        before_effective = self.billing.current_plan_handle(tenant.id)
        before_pending = self._pending_handle(sub)

        if not snapshot.has_active_contract:
            action = self._to_free(tenant, sub, before_effective)
        else:
            action = self._with_contract(tenant, sub, snapshot, before_effective)

        # A scheduled downgrade whose cycle has already ended becomes effective.
        if action == ReconcileAction.UNCHANGED and self.billing.apply_pending_if_due(tenant.id):
            action = ReconcileAction.DOWNGRADE_EFFECTIVE

        effective_after = self.billing.current_plan_handle(tenant.id)
        pending_after = self._pending_handle(self.billing.get_subscription(tenant.id))

        if action != ReconcileAction.UNCHANGED:
            self._write_event(tenant, action, before_effective, effective_after, pending_after, source, snapshot)
        logger.info("billing.reconciled", {"shop": shop_domain, "action": action.value, "effective": effective_after})
        return ReconcileResult(action=action, effective_plan_handle=effective_after, pending_plan_handle=pending_after)

    def _to_free(self, tenant: Tenant, sub, before_effective: str) -> ReconcileAction:
        if sub is None or before_effective == free_plan_handle():
            return ReconcileAction.UNCHANGED
        self.billing.apply_plan_change(
            tenant.id, free_plan_handle(), reset_usage=False, trial_ends_at=None, clear_pending=True
        )
        return ReconcileAction.CANCELLED_TO_FREE

    def _with_contract(self, tenant, sub, snapshot: PartnerSubscriptionSnapshot, before_effective: str) -> ReconcileAction:
        effective = snapshot.effective_plan_handle
        if not effective or plan_by_handle(effective) is None:
            return ReconcileAction.UNCHANGED

        on_trial = self._on_trial(sub)
        first_paid = sub is None or before_effective == free_plan_handle()

        # Downgrade target: an explicit Shopify pendingChange (the usual "downgrade
        # at cycle end"), or a lower effective plan than we currently record.
        downgrade_target: str | None = None
        pending = snapshot.pending_plan_handle
        if pending and plan_by_handle(pending) and classify_change(effective, pending) == "downgrade":
            downgrade_target = pending
        elif not first_paid and classify_change(before_effective, effective) == "downgrade":
            downgrade_target = effective

        if downgrade_target:
            if on_trial:
                # No paid cycle to defer to — apply immediately (the trial-downgrade fix).
                self.billing.apply_plan_change(
                    tenant.id, downgrade_target, reset_usage=False,
                    period_start=snapshot.cycle_start, period_end=snapshot.cycle_end,
                    trial_ends_at=None, clear_pending=True,
                )
                return (
                    ReconcileAction.CANCELLED_TO_FREE
                    if downgrade_target == free_plan_handle()
                    else ReconcileAction.DOWNGRADE_EFFECTIVE
                )
            self.billing.schedule_pending_plan(tenant.id, downgrade_target)
            if downgrade_target == free_plan_handle() or snapshot.cancel_at_end_of_cycle:
                return ReconcileAction.CANCEL_SCHEDULED
            return ReconcileAction.DOWNGRADE_SCHEDULED

        # No downgrade — initial selection / upgrade / renewal.
        if first_paid:
            self.billing.apply_plan_change(
                tenant.id, effective, reset_usage=True,
                period_start=snapshot.cycle_start, period_end=snapshot.cycle_end,
                trial_ends_at=snapshot.trial_ends_at, clear_pending=True,
            )
            return ReconcileAction.INITIAL_SELECTION

        change = classify_change(before_effective, effective)
        if change == "upgrade":
            self.billing.apply_plan_change(
                tenant.id, effective, reset_usage=True,
                period_start=snapshot.cycle_start, period_end=snapshot.cycle_end,
                trial_ends_at=snapshot.trial_ends_at, clear_pending=True,
            )
            return ReconcileAction.UPGRADE_APPLIED

        if change == "same" and snapshot.cycle_end and sub.current_period_end != snapshot.cycle_end:
            self.billing.apply_plan_change(
                tenant.id, effective, reset_usage=True,
                period_start=snapshot.cycle_start, period_end=snapshot.cycle_end,
                trial_ends_at=snapshot.trial_ends_at, clear_pending=True,
            )
            return ReconcileAction.SUBSCRIPTION_RENEWED

        return ReconcileAction.UNCHANGED

    def _write_event(self, tenant, action, before, effective, pending, source, snapshot) -> None:
        self.db.add(
            BillingSubscriptionEvent(
                tenant_id=tenant.id,
                event_type=_ACTION_TO_EVENT[action],
                from_plan_handle=before,
                to_plan_handle=effective,
                effective_plan_handle=effective,
                pending_plan_handle=pending,
                source=source,
                partner_snapshot=snapshot.as_audit(),
            )
        )
        self.db.commit()
