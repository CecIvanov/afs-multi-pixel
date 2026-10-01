"""GDPR compliance: customer data request/redact + shop redact.

`redact_shop_data` deletes every tenant-scoped row in FK-safe order (children
before parents), ending with the tenant itself — the HARD delete, distinct from
the SOFT uninstall in TenantService. `redact_customer_data` deletes the rows tied
to the orders Shopify lists in customers/redact (CUSTOMER_PII_LOCATIONS).
"""

from __future__ import annotations

import uuid
from typing import Any, Callable

from sqlalchemy import ColumnElement, and_, delete
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import (
    AsyncJob,
    AsyncJobOperation,
    BillingSubscriptionEvent,
    MarketPixel,
    PendingPurchase,
    ServerEvent,
    Tenant,
    TenantMetadata,
    TenantSubscription,
    UsageCounter,
    WebhookEvent,
    purchase_event_id,
)
from app.services.tenant_service import TenantService

logger = get_logger().child({"component": "compliance"})

OrderFilter = Callable[[uuid.UUID, list[int]], ColumnElement[bool]]


def _order_payload_in(payload_column: Any, orders: list[int]) -> ColumnElement[bool]:
    """A stored orders/create payload whose order ``id`` is one of ``orders``."""
    return payload_column["id"].astext.in_([str(o) for o in orders])


# Every row tied to a customer, located by Shopify order ID (customers/redact
# lists orders_to_redact). Server Events and pending Purchases hold only hashed
# data; a raw orders/create still waiting in the inbox holds it in the clear.
# Jobs go before webhook events (a job references its webhook event).
CUSTOMER_PII_LOCATIONS: tuple[tuple[type, OrderFilter], ...] = (
    (
        ServerEvent,
        lambda tenant_id, orders: and_(
            ServerEvent.tenant_id == tenant_id, ServerEvent.event_id.in_([purchase_event_id(o) for o in orders])
        ),
    ),
    (
        PendingPurchase,
        lambda tenant_id, orders: and_(PendingPurchase.tenant_id == tenant_id, PendingPurchase.order_id.in_(orders)),
    ),
    (
        AsyncJob,
        lambda tenant_id, orders: and_(
            AsyncJob.tenant_id == tenant_id,
            AsyncJob.operation == AsyncJobOperation.ORDERS_CREATE,
            _order_payload_in(AsyncJob.payload, orders),
        ),
    ),
    (
        WebhookEvent,
        lambda tenant_id, orders: and_(
            WebhookEvent.tenant_id == tenant_id,
            WebhookEvent.topic == "orders/create",
            _order_payload_in(WebhookEvent.payload, orders),
        ),
    ),
)

# Tenant-scoped tables in FK-safe delete order for shop/redact (the tenant row
# goes last). Several have no ON DELETE CASCADE off the tenant row.
SHOP_TABLES: tuple[type, ...] = (
    AsyncJob,
    WebhookEvent,
    ServerEvent,
    PendingPurchase,
    MarketPixel,
    BillingSubscriptionEvent,
    UsageCounter,
    TenantMetadata,
    TenantSubscription,
)

# What a customers/data_request gets: the app keeps nothing that identifies a
# customer (spec §7), so the answer is always the same.
DATA_REQUEST_REPLY = (
    "AFS Multi Pixel holds no data that identifies this customer. It sends the store's "
    "own conversion events to the store's Meta pixels; customer contact and address data "
    "is hashed before it is stored, and raw order data is deleted once it is processed."
)


class ComplianceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def export_customer_data(
        self,
        *,
        shop_domain: str,
        shopify_customer_id: int | None = None,
        orders_requested: list[int] | None = None,
    ) -> dict[str, Any]:
        logger.info(
            "compliance.customer_data_request",
            {
                "shop": shop_domain,
                "customerId": shopify_customer_id,
                "ordersRequested": orders_requested or [],
                "reply": DATA_REQUEST_REPLY,
            },
        )
        return {
            "shop_domain": shop_domain,
            "customer_id": shopify_customer_id,
            "orders_requested": orders_requested or [],
            "records": [],
            "reply": DATA_REQUEST_REPLY,
        }

    def redact_customer_data(
        self, *, shop_domain: str, orders_to_redact: list[int], shopify_customer_id: int | None = None
    ) -> int:
        tenant = TenantService(self.db).get_tenant_by_shop_domain(shop_domain)
        if not tenant or not orders_to_redact:
            logger.info("compliance.customer_redact.nothing", {"shop": shop_domain, "customerId": shopify_customer_id})
            return 0
        deleted = 0
        for model, where in CUSTOMER_PII_LOCATIONS:
            result = self.db.execute(delete(model).where(where(tenant.id, orders_to_redact)))
            deleted += int(result.rowcount or 0)
        self.db.commit()
        logger.info(
            "compliance.customer_redact.done",
            {"shop": shop_domain, "customerId": shopify_customer_id, "orders": len(orders_to_redact), "rows": deleted},
        )
        return deleted

    def redact_shop_data(self, shop_domain: str) -> bool:
        """HARD delete every tenant-scoped row + the tenant."""
        tenant = TenantService(self.db).get_tenant_by_shop_domain(shop_domain)
        if not tenant:
            logger.info("compliance.shop_redact.ignored", {"shop": shop_domain, "reason": "tenant_not_found"})
            return False
        tenant_id = tenant.id

        for model in SHOP_TABLES:
            self.db.execute(delete(model).where(model.tenant_id == tenant_id))
        self.db.execute(delete(Tenant).where(Tenant.id == tenant_id))
        self.db.commit()
        logger.info("compliance.shop_redact.done", {"shop": shop_domain, "tenantId": str(tenant_id)})
        return True
