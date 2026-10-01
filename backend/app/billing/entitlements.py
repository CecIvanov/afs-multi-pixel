"""Rank-based feature gates. A feature is granted when the tenant's current plan
rank is at least the lowest rank of any plan that lists the feature."""

from __future__ import annotations

from functools import lru_cache

from app.billing.plan_catalog import get_plans, rank_of, top_plan_handle
from app.config import get_settings


@lru_cache
def _feature_min_rank() -> dict[str, int]:
    out: dict[str, int] = {}
    for plan in get_plans():
        for feature in plan.features:
            out[feature] = min(out.get(feature, plan.rank), plan.rank)
    return out


def effective_plan_handle(current_handle: str | None) -> str:
    """The plan whose entitlements actually apply. With enforcement OFF, every
    tenant is treated as the top plan so all gates open (dev / UAT / incident)."""
    if not get_settings().billing_enforcement_enabled:
        return top_plan_handle()
    return current_handle or ""


def has_feature(current_handle: str | None, feature: str) -> bool:
    min_rank = _feature_min_rank().get(feature)
    if min_rank is None:
        return False  # feature not offered by any plan
    return rank_of(effective_plan_handle(current_handle)) >= min_rank


class FeatureNotEntitled(Exception):
    def __init__(self, feature: str) -> None:
        super().__init__(f"Feature '{feature}' is not available on the current plan")
        self.feature = feature


def ensure_feature(current_handle: str | None, feature: str) -> None:
    if not has_feature(current_handle, feature):
        raise FeatureNotEntitled(feature)
