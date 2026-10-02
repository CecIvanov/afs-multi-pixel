"""Tenant install/session/uninstall lifecycle + shop-info capture."""

from __future__ import annotations

import pytest

from tests.conftest import INTERNAL_HEADERS

INSTALL = {
    "shop_domain": "demo-shop.myshopify.com",
    "access_token": "shpat_token_1",
    "scopes": "write_products",
}


@pytest.mark.integration
def test_install_creates_tenant_with_plan(client):
    r = client.post("/api/v1/internal/shopify/install", json=INSTALL, headers=INTERNAL_HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["shop_domain"] == "demo-shop.myshopify.com"
    assert body["status"] == "active"
    assert body["plan_handle"] == "none"  # no plan chosen yet (app.config.json billing)
    assert body["installed_at"] is not None


@pytest.mark.integration
def test_install_requires_internal_key(client):
    r = client.post("/api/v1/internal/shopify/install", json=INSTALL)
    assert r.status_code == 401


@pytest.mark.integration
def test_by_shop_lookup_and_normalization(client):
    client.post("/api/v1/internal/shopify/install", json=INSTALL, headers=INTERNAL_HEADERS)
    # Look up without the .myshopify.com suffix — should normalize and find it.
    r = client.get("/api/v1/internal/tenants/by-shop/demo-shop", headers=INTERNAL_HEADERS)
    assert r.status_code == 200
    assert r.json()["shop_domain"] == "demo-shop.myshopify.com"


@pytest.mark.integration
def test_session_sync_updates_token(client):
    client.post("/api/v1/internal/shopify/install", json=INSTALL, headers=INTERNAL_HEADERS)
    r = client.post(
        "/api/v1/internal/shopify/session-sync",
        json={**INSTALL, "access_token": "shpat_token_2"},
        headers=INTERNAL_HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "active"


@pytest.mark.integration
def test_uninstall_is_soft_then_reinstall_reactivates(client, db):
    # Uninstall now flows through the webhook queue -> APP_UNINSTALL job, which
    # calls TenantService.sync_shopify_uninstall (exercised directly here).
    from app.models import Tenant, TenantStatus
    from app.services.tenant_service import TenantService

    client.post("/api/v1/internal/shopify/install", json=INSTALL, headers=INTERNAL_HEADERS)

    t = TenantService(db).sync_shopify_uninstall(INSTALL["shop_domain"])
    assert t is not None
    # Soft: row kept, status uninstalled, tokens nulled.
    db.expire_all()
    t = db.get(Tenant, t.id)
    assert t.status == TenantStatus.UNINSTALLED and t.access_token is None
    tenant_id_before = t.id

    # Reinstall reactivates the SAME row (no duplicate).
    r2 = client.post("/api/v1/internal/shopify/install", json=INSTALL, headers=INTERNAL_HEADERS)
    assert r2.status_code == 200 and r2.json()["status"] == "active"
    assert r2.json()["id"] == str(tenant_id_before)


@pytest.mark.integration
def test_uninstall_unknown_shop_is_ignored(db):
    from app.services.tenant_service import TenantService

    assert TenantService(db).sync_shopify_uninstall("nobody.myshopify.com") is None


# --- shop-info capture (pure logic, no network) -----------------------------
@pytest.mark.unit
def test_build_store_info_metadata_keeps_present_values_only():
    from app.services.shopify_shop_info_service import build_store_info_metadata

    shop = {
        "name": "Demo Shop",
        "contactEmail": "owner@demo.example",
        "billingAddress": {"phone": "  +359888123456 ", "countryCodeV2": "BG"},
        "plan": {"displayName": "Shopify"},
    }
    meta = build_store_info_metadata(shop)
    assert meta == {
        "store_name": "Demo Shop",
        "store_contact_email": "owner@demo.example",
        "store_phone": "+359888123456",
        "store_country_code": "BG",
        "shop_plan_display_name": "Shopify",
    }


@pytest.mark.unit
def test_build_store_info_metadata_drops_missing():
    from app.services.shopify_shop_info_service import build_store_info_metadata

    assert build_store_info_metadata({"name": "Only Name"}) == {"store_name": "Only Name"}
    assert build_store_info_metadata(None) == {}


@pytest.mark.integration
def test_upsert_tenant_metadata_never_wipes(client, db):
    from app.services.shopify_shop_info_service import upsert_tenant_metadata
    from app.services.tenant_service import TenantService

    client.post("/api/v1/internal/shopify/install", json=INSTALL, headers=INTERNAL_HEADERS)
    tenant = TenantService(db).get_tenant_by_shop_domain(INSTALL["shop_domain"])

    upsert_tenant_metadata(db, tenant.id, {"store_name": "First", "store_phone": "123"})
    db.commit()
    upsert_tenant_metadata(db, tenant.id, {"store_name": "Second"})  # phone absent
    db.commit()

    from app.models import TenantMetadata
    from sqlalchemy import select

    rows = {
        m.m_key: m.m_value
        for m in db.scalars(select(TenantMetadata).where(TenantMetadata.tenant_id == tenant.id))
    }
    assert rows["store_name"] == "Second"   # updated
    assert rows["store_phone"] == "123"     # NOT wiped
