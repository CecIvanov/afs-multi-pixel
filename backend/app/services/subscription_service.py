"""The one paid plan (spec §1, §5). The app knows only the plan's exact name (from
app.config.json ``billing.plan``, or BILLING_PLAN_NAME) and whether the shop's
subscription to it is active; never an amount. A shop known to have no active
subscription gets no Relays accepted. NULL means "not checked yet" and passes.
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy.orm import Session

from app.app_config import get_app_config
from app.logging_config import get_logger
from app.models import Tenant

logger = get_logger().child({"component": "subscription"})


def plan_name() -> str:
    configured = (get_app_config().raw.get("billing", {}).get("plan") or {}).get("name")
    return os.environ.get("BILLING_PLAN_NAME") or configured or "AFS Multi Pixel"


def is_plan_subscription_active(subscription: dict[str, Any]) -> bool:
    return (
        str(subscription.get("name") or "") == plan_name()
        and str(subscription.get("status") or "").upper() == "ACTIVE"
    )


def set_subscription_active(db: Session, tenant: Tenant, active: bool) -> None:
    if tenant.subscription_active != active:
        logger.info("subscription.changed", {"tenantId": str(tenant.id), "active": active})
    tenant.subscription_active = active
    db.commit()
