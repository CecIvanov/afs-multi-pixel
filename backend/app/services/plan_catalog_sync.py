"""Mirror the plan catalog (app.config.json billing.plans) into billing_plans, so
every plan a subscription can point at exists in the database. Idempotent; runs
on API start (a new plan needs only the config change and a deploy)."""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.billing import plan_catalog
from app.models import BillingPlan


def sync_plan_catalog(db: Session) -> int:
    plans = plan_catalog.get_plans()
    for plan in plans:
        values = {"name": plan.name, "monthly_quota": plan.monthly_quota, "shopify_plan_name": plan.shopify_plan_name}
        db.execute(
            pg_insert(BillingPlan)
            .values(handle=plan.handle, **values)
            .on_conflict_do_update(index_elements=["handle"], set_=values)
        )
    db.commit()
    return len(plans)
