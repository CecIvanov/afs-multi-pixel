"""Turn a verified Shopify webhook into a durable job.

Node verifies HMAC then POSTs here; this records a WebhookEvent (delivery-level
dedup) and enqueues one job (work-level dedup via the pending index), returning
fast. Lifecycle/compliance topics return 2xx even when the tenant is gone.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import AsyncJobOperation, TenantStatus
from app.services.async_job_service import AsyncJobService
from app.services.tenant_service import TenantService
from app.services.webhook_event_service import WebhookEventService

logger = get_logger().child({"component": "webhook_ingest"})

TOPIC_TO_OPERATION: dict[str, AsyncJobOperation] = {
    "app/uninstalled": AsyncJobOperation.APP_UNINSTALL,
    "app/scopes_update": AsyncJobOperation.SCOPES_UPDATE,
    "shop/redact": AsyncJobOperation.SHOP_REDACT,
    "customers/data_request": AsyncJobOperation.CUSTOMER_DATA_REQUEST,
    "customers/redact": AsyncJobOperation.CUSTOMER_REDACT,
    "orders/create": AsyncJobOperation.ORDERS_CREATE,
    # One re-fetch covers any Market change, so the three coalesce into one job.
    "markets/create": AsyncJobOperation.MARKETS_SYNC,
    "markets/update": AsyncJobOperation.MARKETS_SYNC,
    "markets/delete": AsyncJobOperation.MARKETS_SYNC,
}

# These must return 2xx to Shopify even when the shop row is unknown (already
# uninstalled, or the webhook beat backend provisioning).
IDEMPOTENT_MISSING_TENANT_OPERATIONS = frozenset(
    {
        AsyncJobOperation.APP_UNINSTALL,
        AsyncJobOperation.SHOP_REDACT,
        AsyncJobOperation.CUSTOMER_DATA_REQUEST,
        AsyncJobOperation.CUSTOMER_REDACT,
    }
)
# Ops allowed even when the tenant isn't active (uninstalled shops still get redacted).
INACTIVE_TENANT_ALLOWED_OPERATIONS = IDEMPOTENT_MISSING_TENANT_OPERATIONS


def normalize_webhook_topic(topic: str) -> str:
    """"app/scopes_update" stays as is; the storage form "APP_SCOPES_UPDATE" that
    authenticate.webhook returns becomes "app/scopes_update" — only the first
    underscore is the resource separator."""
    raw = topic.strip().lower()
    return raw if "/" in raw else raw.replace("_", "/", 1)


@dataclass(frozen=True)
class WebhookIngestResult:
    status: str
    duplicate: bool = False
    job_id: uuid.UUID | None = None
    webhook_event_id: uuid.UUID | None = None


def _dedupe_key(operation: AsyncJobOperation, payload: dict[str, Any] | None) -> str:
    payload = payload or {}
    customer_id = (payload.get("customer") or {}).get("id") or payload.get("customer_email") or "unknown"
    if operation == AsyncJobOperation.CUSTOMER_REDACT:
        # Two redacts for one customer may list different orders; coalescing them
        # would drop the first one's orders, so the orders are part of the key.
        orders = ",".join(sorted(str(o) for o in payload.get("orders_to_redact") or []))
        return f"{operation.value}:{customer_id}:{hashlib.sha256(orders.encode()).hexdigest()[:16]}"
    if operation == AsyncJobOperation.CUSTOMER_DATA_REQUEST:
        return f"{operation.value}:{customer_id}"
    if operation == AsyncJobOperation.ORDERS_CREATE:
        return f"{operation.value}:{payload.get('id', 'unknown')}"
    return operation.value


class WebhookIngestService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.tenants = TenantService(db)
        self.jobs = AsyncJobService(db)
        self.webhooks = WebhookEventService(db)

    def ingest(
        self,
        *,
        shop_domain: str,
        topic: str,
        shopify_webhook_id: str | None = None,
        payload: dict[str, Any] | None = None,
        webhook_context: dict[str, Any] | None = None,
    ) -> WebhookIngestResult:
        normalized = normalize_webhook_topic(topic)
        operation = TOPIC_TO_OPERATION.get(normalized)
        if operation is None:
            raise ValueError(f"Unsupported webhook topic: {topic}")

        tenant = self.tenants.get_tenant_by_shop_domain(shop_domain)
        if not tenant:
            if operation in IDEMPOTENT_MISSING_TENANT_OPERATIONS:
                logger.info("webhook.ingest.ignored", {"topic": normalized, "shop": shop_domain, "reason": "tenant_not_found"})
                return WebhookIngestResult(status="ignored")
            raise ValueError("Tenant not found")

        if tenant.status != TenantStatus.ACTIVE and operation not in INACTIVE_TENANT_ALLOWED_OPERATIONS:
            raise ValueError("Tenant is not active")

        # Delivery-level dedup on the Shopify webhook id.
        webhook_event = None
        if shopify_webhook_id:
            webhook_event = self.webhooks.record_received(
                shopify_webhook_id=shopify_webhook_id, topic=normalized, tenant_id=tenant.id, payload=payload or {}
            )
            if webhook_event is None:
                return WebhookIngestResult(status="duplicate", duplicate=True)

        job_payload: dict[str, Any] = dict(payload or {})
        if webhook_context:
            job_payload["webhook_context"] = webhook_context

        job = self.jobs.enqueue(
            tenant_id=tenant.id,
            operation=operation,
            topic=normalized,
            dedupe_key=_dedupe_key(operation, payload),
            shopify_webhook_id=shopify_webhook_id,
            webhook_event_id=webhook_event.id if webhook_event else None,
            payload=job_payload or None,
        )
        self.db.commit()
        logger.info("webhook.ingested", {"topic": normalized, "jobId": str(job.id)})
        return WebhookIngestResult(
            status="accepted", job_id=job.id, webhook_event_id=webhook_event.id if webhook_event else None
        )
