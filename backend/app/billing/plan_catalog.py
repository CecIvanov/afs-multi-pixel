"""Plan catalog + pure semantics, driven from app.config.json (billing.plans).

The catalog mirrors the plans you define in the Shopify Partner Dashboard. Display
names are decoupled from stable handles: a merchant may see "Pro" while the handle
stays `pro`, so `normalize_shopify_plan_name` fuzzily maps a Shopify plan/display
name back to a handle (renaming a plan in the Dashboard must not break resolution).

Mirrored by shopify/app/billing.shared.mjs (a parity test — Phase 4 — guards drift).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.app_config import get_app_config


@dataclass(frozen=True)
class PlanSpec:
    handle: str
    name: str
    rank: int
    shopify_plan_name: str | None
    monthly_quota: int | None
    features: tuple[str, ...]


@lru_cache
def get_plans() -> tuple[PlanSpec, ...]:
    raw = get_app_config().raw.get("billing", {}).get("plans", [])
    plans = [
        PlanSpec(
            handle=p["handle"],
            name=p.get("name", p["handle"]),
            rank=int(p.get("rank", 0)),
            shopify_plan_name=p.get("shopifyPlanName"),
            monthly_quota=p.get("monthlyQuota"),
            features=tuple(p.get("features", [])),
        )
        for p in raw
    ]
    return tuple(sorted(plans, key=lambda p: p.rank))


def plan_by_handle(handle: str | None) -> PlanSpec | None:
    if not handle:
        return None
    return next((p for p in get_plans() if p.handle == handle), None)


@lru_cache
def free_plan_handle() -> str:
    cfg = get_app_config().raw.get("billing", {})
    return cfg.get("freePlanHandle") or (get_plans()[0].handle if get_plans() else "free")


@lru_cache
def top_plan_handle() -> str:
    cfg = get_app_config().raw.get("billing", {})
    return cfg.get("topPlanHandle") or (get_plans()[-1].handle if get_plans() else "pro")


def rank_of(handle: str | None) -> int:
    plan = plan_by_handle(handle)
    return plan.rank if plan else 0


def normalize_shopify_plan_name(raw: str | None) -> str | None:
    """Map a Shopify plan / display name to a canonical handle, or None."""
    norm = str(raw or "").strip().lower()
    if not norm:
        return None
    for plan in get_plans():
        candidates = {plan.handle.lower(), plan.name.lower()}
        if plan.shopify_plan_name:
            candidates.add(plan.shopify_plan_name.lower())
        if norm in candidates:
            return plan.handle
    # Loose contains-match as a fallback (handles "MyApp Pro" -> pro).
    for plan in sorted(get_plans(), key=lambda p: -p.rank):
        if plan.handle.lower() in norm or plan.name.lower() in norm:
            return plan.handle
    return None


def classify_change(from_handle: str | None, to_handle: str | None) -> str:
    """'same' | 'upgrade' | 'downgrade' by rank."""
    if not to_handle or from_handle == to_handle:
        return "same"
    fr, to = rank_of(from_handle), rank_of(to_handle)
    if to > fr:
        return "upgrade"
    if to < fr:
        return "downgrade"
    return "same"
