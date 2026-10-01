"""GDPR compliance: customer data export/redact + shop redact.

`redact_shop_data` deletes every tenant-scoped row in FK-safe order (children
before parents), ending with the tenant itself — the HARD delete, distinct from
the SOFT uninstall in TenantService. Customer export/redact are stubs: fill in
CUSTOMER_PII_LOCATIONS with your app's customer-bearing tables.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import (
    AsyncJob,
    TenantMetadata,
    TenantSubscription,
    WebhookEvent,
)
from app.services.tenant_service import TenantService

logger = get_logger().child({"component": "compliance"})

# Fill in with your app's tables/columns that hold customer PII, keyed by how you
# locate a customer (shopify_customer_id / email). Used by redact_customer_data.
CUSTOMER_PII_LOCATIONS: tuple[str, ...] = ()


class ComplianceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def export_customer_data(
        self, *, shop_domain: str, shopify_customer_id: int | None = None, customer_email: str | None = None
    ) -> dict[str, Any]:
        # Return whatever customer-linked data your app stores. Stub: nothing yet.
        logger.info("compliance.customer_data_request", {"shop": shop_domain, "customerId": shopify_customer_id})
        return {"shop_domain": shop_domain, "customer_id": shopify_customer_id, "records": []}

    def redact_customer_data(
        self, *, shop_domain: str, shopify_customer_id: int | None = None, customer_email: str | None = None
    ) -> int:
        # Delete/anonymize customer PII in CUSTOMER_PII_LOCATIONS. Stub: 0 rows.
        logger.info("compliance.customer_redact", {"shop": shop_domain, "customerId": shopify_customer_id})
        return 0

    def redact_shop_data(self, shop_domain: str) -> bool:
        """HARD delete every tenant-scoped row + the tenant. FK-safe order matters:
        several child tables have no ON DELETE CASCADE off the tenant row."""
        tenant = TenantService(self.db).get_tenant_by_shop_domain(shop_domain)
        if not tenant:
            logger.info("compliance.shop_redact.ignored", {"shop": shop_domain, "reason": "tenant_not_found"})
            return False
        tenant_id = tenant.id

        # Children / tenant-scoped tables first, tenant row last.
        self.db.execute(delete(AsyncJob).where(AsyncJob.tenant_id == tenant_id))
        self.db.execute(delete(WebhookEvent).where(WebhookEvent.tenant_id == tenant_id))
        self.db.execute(delete(TenantMetadata).where(TenantMetadata.tenant_id == tenant_id))
        self.db.execute(delete(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id))
        # ... add your app's tenant-scoped tables here (before the tenant delete) ...
        from app.models import Tenant

        self.db.execute(delete(Tenant).where(Tenant.id == tenant_id))
        self.db.commit()
        logger.info("compliance.shop_redact.done", {"shop": shop_domain, "tenantId": str(tenant_id)})
        return True
