"""Capture the Shopify store profile (name / contact / phone / country / plan)
into tenants_metadata. Best-effort, async, never on the install critical path.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.app_config import get_app_config
from app.logging_config import get_logger
from app.models import Tenant, TenantMetadata

logger = get_logger().child({"component": "shopify_shop_info"})

STORE_INFO_SYNCED_AT_KEY = "store_info_synced_at"

# `shop` is readable by any authenticated Admin session — no extra scope needed.
SHOP_INFO_QUERY = """
query ShopInfo {
  shop {
    name
    contactEmail
    billingAddress { phone countryCodeV2 }
    plan { displayName }
  }
}
"""


class ShopifyShopInfoError(RuntimeError):
    pass


def _api_version() -> str:
    return get_app_config().raw.get("shopify", {}).get("apiVersion", "2026-10")


def tenant_can_call_admin_api(tenant: Tenant) -> bool:
    # Canonical gate lives in shopify_tenant_credentials — also refuses a tenant
    # whose offline refresh chain is revoked (no live token to call with).
    from app.services.shopify_tenant_credentials import (
        tenant_can_call_admin_api as _can_call,
    )

    return _can_call(tenant)


def build_store_info_metadata(shop: dict[str, Any] | None) -> dict[str, str]:
    """Map a Shopify `shop` node to tenant_metadata keys. Only present, non-empty
    values are returned (a store with no phone simply yields no store_phone row)."""
    shop = shop or {}
    billing = shop.get("billingAddress") or {}
    plan = shop.get("plan") or {}
    candidates = {
        "store_name": shop.get("name"),
        "store_contact_email": shop.get("contactEmail"),
        "store_phone": billing.get("phone"),
        "store_country_code": billing.get("countryCodeV2"),
        "shop_plan_display_name": plan.get("displayName"),
    }
    return {k: str(v).strip() for k, v in candidates.items() if v is not None and str(v).strip()}


def upsert_tenant_metadata(db: Session, tenant_id: uuid.UUID, values: dict[str, str]) -> None:
    """Insert-or-update one row per key. Never deletes keys absent from `values`,
    so a transient missing field can't wipe a previously-captured value."""
    for key, value in values.items():
        row = db.scalar(
            select(TenantMetadata).where(
                TenantMetadata.tenant_id == tenant_id, TenantMetadata.m_key == key
            )
        )
        if row is None:
            db.add(TenantMetadata(tenant_id=tenant_id, m_key=key, m_value=value))
        else:
            row.m_value = value


def admin_graphql(
    *, shop_domain: str, access_token: str, query: str, variables: dict[str, Any] | None = None
) -> dict[str, Any]:
    version = _api_version()
    url = f"https://{shop_domain.strip().lower()}/admin/api/{version}/graphql.json"
    try:
        response = httpx.post(
            url,
            json={"query": query, "variables": variables or {}},
            headers={"X-Shopify-Access-Token": access_token, "Content-Type": "application/json"},
            timeout=30.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        body = exc.response.text[:500] if exc.response is not None else ""
        raise ShopifyShopInfoError(f"Shopify API HTTP {status}: {body or exc}") from exc
    except httpx.HTTPError as exc:
        raise ShopifyShopInfoError(f"Shopify API request failed: {exc}") from exc

    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise ShopifyShopInfoError(f"Shopify API returned invalid JSON: {response.text[:500]}") from exc

    if payload.get("errors"):
        message = "; ".join(str(err.get("message") or err) for err in payload.get("errors") or [])
        raise ShopifyShopInfoError(message or "Shopify GraphQL error")
    return payload


def execute_shop_info_fetch_for_tenant(db: Session, tenant: Tenant) -> bool:
    """Fetch the store profile and upsert it into tenants_metadata.

    Returns False (no raise) when the tenant can't call the Admin API. Shopify /
    transport errors propagate so the worker records + retries them.
    """
    if not tenant_can_call_admin_api(tenant):
        logger.info("shopify_shop_info.skipped_no_admin_access", {"tenantId": str(tenant.id)})
        return False

    payload = admin_graphql(
        shop_domain=tenant.shop_domain, access_token=tenant.access_token or "", query=SHOP_INFO_QUERY
    )
    shop = (payload.get("data") or {}).get("shop") or {}
    values = build_store_info_metadata(shop)
    values[STORE_INFO_SYNCED_AT_KEY] = datetime.now(UTC).isoformat()
    upsert_tenant_metadata(db, tenant.id, values)
    db.commit()
    logger.info(
        "shopify_shop_info.captured",
        {"tenantId": str(tenant.id), "shop": tenant.shop_domain, "keys": sorted(values.keys())},
    )
    return True
