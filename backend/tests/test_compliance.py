"""GDPR shop redaction — hard delete of every tenant-scoped row."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models import (
    AsyncJob,
    Tenant,
    TenantMetadata,
    TenantSubscription,
    WebhookEvent,
)
from app.services.compliance_service import ComplianceService
from app.services.tenant_service import TenantService

SHOP = "redact-shop.myshopify.com"


@pytest.mark.integration
def test_redact_shop_data_deletes_all_tenant_rows(db):
    tenant = TenantService(db).sync_shopify_install(SHOP, access_token="tok")
    tid = tenant.id
    db.add(TenantMetadata(tenant_id=tid, m_key="store_name", m_value="Demo"))
    db.add(WebhookEvent(tenant_id=tid, topic="shop/redact", shopify_webhook_id="w-red", payload={}))
    db.commit()

    assert db.scalar(select(func.count()).select_from(TenantSubscription).where(TenantSubscription.tenant_id == tid)) == 1

    ok = ComplianceService(db).redact_shop_data(SHOP)
    assert ok is True

    assert db.get(Tenant, tid) is None
    for model in (TenantMetadata, TenantSubscription, WebhookEvent, AsyncJob):
        remaining = db.scalar(select(func.count()).select_from(model).where(model.tenant_id == tid))
        assert remaining == 0, model.__tablename__


@pytest.mark.integration
def test_redact_unknown_shop_is_ignored(db):
    assert ComplianceService(db).redact_shop_data("nobody.myshopify.com") is False
