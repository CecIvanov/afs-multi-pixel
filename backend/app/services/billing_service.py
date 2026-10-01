"""Billing enforcement + subscription mutations + metered usage.

Plan identity is config-driven (billing/plan_catalog.py). This service owns the
DB state: the tenant's subscription, its pending plan, trial window, and a monthly
usage counter with an atomic increment guard.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.billing import entitlements
from app.billing.plan_catalog import free_plan_handle, plan_by_handle
from app.models import BillingPlan, SubscriptionStatus, TenantSubscription, UsageCounter
from app.reference_data import default_subscription_period

# Three-state sentinel: leave trial untouched vs explicitly clear vs set a value.
_UNSET = object()


class QuotaExceeded(Exception):
    pass


class BillingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- reads ---------------------------------------------------------------
    def get_subscription(self, tenant_id: uuid.UUID) -> TenantSubscription | None:
        return self.db.scalar(select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id))

    def current_plan_handle(self, tenant_id: uuid.UUID) -> str:
        sub = self.get_subscription(tenant_id)
        if not sub:
            return free_plan_handle()
        plan = self.db.get(BillingPlan, sub.billing_plan_id)
        return plan.handle if plan else free_plan_handle()

    def effective_plan_handle(self, tenant_id: uuid.UUID) -> str:
        return entitlements.effective_plan_handle(self.current_plan_handle(tenant_id))

    def has_feature(self, tenant_id: uuid.UUID, feature: str) -> bool:
        return entitlements.has_feature(self.current_plan_handle(tenant_id), feature)

    def ensure_feature(self, tenant_id: uuid.UUID, feature: str) -> None:
        entitlements.ensure_feature(self.current_plan_handle(tenant_id), feature)

    def _plan_row(self, handle: str) -> BillingPlan | None:
        return self.db.scalar(select(BillingPlan).where(BillingPlan.handle == handle))

    # --- subscription mutations ---------------------------------------------
    def apply_plan_change(
        self,
        tenant_id: uuid.UUID,
        plan_handle: str,
        *,
        reset_usage: bool = False,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        trial_ends_at: Any = _UNSET,
        clear_pending: bool = True,
    ) -> TenantSubscription:
        plan = self._plan_row(plan_handle)
        if plan is None:
            raise ValueError(f"Unknown plan '{plan_handle}'")
        sub = self.get_subscription(tenant_id)
        start, end = default_subscription_period()
        if sub is None:
            sub = TenantSubscription(
                tenant_id=tenant_id, billing_plan_id=plan.id, status=SubscriptionStatus.ACTIVE,
                current_period_start=period_start or start, current_period_end=period_end or end,
            )
            self.db.add(sub)
        else:
            sub.billing_plan_id = plan.id
            sub.status = SubscriptionStatus.ACTIVE
            if period_start is not None:
                sub.current_period_start = period_start
            if period_end is not None:
                sub.current_period_end = period_end
        if clear_pending:
            sub.pending_billing_plan_id = None
        if trial_ends_at is not _UNSET:
            sub.trial_ends_at = trial_ends_at
        self.db.flush()
        if reset_usage:
            self._reset_usage(tenant_id, plan)
        self.db.commit()
        self.db.refresh(sub)
        return sub

    def schedule_pending_plan(self, tenant_id: uuid.UUID, plan_handle: str) -> TenantSubscription | None:
        plan = self._plan_row(plan_handle)
        sub = self.get_subscription(tenant_id)
        if plan is None or sub is None:
            return sub
        sub.pending_billing_plan_id = plan.id
        self.db.commit()
        self.db.refresh(sub)
        return sub

    def apply_pending_if_due(self, tenant_id: uuid.UUID) -> bool:
        """Apply a scheduled downgrade once the current cycle has ended."""
        sub = self.get_subscription(tenant_id)
        if not sub or sub.pending_billing_plan_id is None:
            return False
        period_end = sub.current_period_end
        if period_end and period_end.tzinfo is None:
            period_end = period_end.replace(tzinfo=UTC)
        if period_end and datetime.now(UTC) < period_end:
            return False
        pending = self.db.get(BillingPlan, sub.pending_billing_plan_id)
        if pending is None:
            return False
        self.apply_plan_change(tenant_id, pending.handle, clear_pending=True)
        return True

    # --- metered usage -------------------------------------------------------
    @staticmethod
    def _period_start(today: date | None = None) -> date:
        d = today or datetime.now(UTC).date()
        return d.replace(day=1)

    def _reset_usage(self, tenant_id: uuid.UUID, plan: BillingPlan) -> None:
        period = self._period_start()
        counter = self.db.scalar(
            select(UsageCounter).where(UsageCounter.tenant_id == tenant_id, UsageCounter.period_start == period)
        )
        quota = plan.monthly_quota if plan.monthly_quota is not None else 2_000_000_000
        if counter is None:
            self.db.add(UsageCounter(tenant_id=tenant_id, period_start=period, used=0, quota=quota))
        else:
            counter.used = 0
            counter.quota = quota

    def _ensure_counter(self, tenant_id: uuid.UUID) -> UsageCounter:
        period = self._period_start()
        counter = self.db.scalar(
            select(UsageCounter).where(UsageCounter.tenant_id == tenant_id, UsageCounter.period_start == period)
        )
        if counter is None:
            plan = self._plan_row(self.current_plan_handle(tenant_id))
            quota = (plan.monthly_quota if plan and plan.monthly_quota is not None else 2_000_000_000)
            counter = UsageCounter(tenant_id=tenant_id, period_start=period, used=0, quota=quota)
            self.db.add(counter)
            self.db.commit()
        return counter

    def try_consume(self, tenant_id: uuid.UUID, amount: int = 1) -> bool:
        """Atomically consume `amount` of quota. Returns False if it would exceed —
        the UPDATE ... WHERE used+amount<=quota RETURNING guard is race-safe."""
        self._ensure_counter(tenant_id)
        period = self._period_start()
        row = self.db.execute(
            text(
                """
                UPDATE usage_counters SET used = used + :amount
                WHERE tenant_id = :tid AND period_start = :period AND used + :amount <= quota
                RETURNING used
                """
            ),
            {"amount": amount, "tid": str(tenant_id), "period": period},
        ).first()
        self.db.commit()
        return row is not None

    def ensure_within_quota(self, tenant_id: uuid.UUID, amount: int = 1) -> None:
        if not self.try_consume(tenant_id, amount):
            raise QuotaExceeded("Monthly quota exceeded on the current plan")
