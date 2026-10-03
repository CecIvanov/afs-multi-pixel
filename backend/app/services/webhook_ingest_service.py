"""Store a verified Shopify webhook and hand it to the worker.

Node verifies the HMAC then POSTs here; this ALWAYS stores the webhook as a
WebhookEvent (delivery-level dedup on Shopify's webhook id) and answers, so
Shopify gets its 200. It decides nothing: when the topic has a job and the shop
has a tenant, one job is enqueued (work-level dedup via the pending index) and
the worker decides what to do — including skipping work for an uninstalled
tenant. A webhook with no job to run (unknown shop or topic) stays stored with
the reason.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import AsyncJobOperation
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

# Operations the worker still runs for a tenant that isn't active (uninstalled
# shops still get redacted). See job_processors.dispatch_job.
INACTIVE_TENANT_ALLOWED_OPERATIONS = frozenset(
    {
        AsyncJobOperation.APP_UNINSTALL,
        AsyncJobOperation.SHOP_REDACT,
        AsyncJobOperation.CUSTOMER_DATA_REQUEST,
        AsyncJobOperation.CUSTOMER_REDACT,
    }
)


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
        tenant = self.tenants.get_tenant_by_shop_domain(shop_domain)

        # Store first, always. Delivery-level dedup on the Shopify webhook id.
        webhook_event = self.webhooks.record_received(
            shopify_webhook_id=shopify_webhook_id or f"local-{uuid.uuid4()}",
            topic=normalized,
            tenant_id=tenant.id if tenant else None,
            payload=payload or {},
        )
        if webhook_event is None:
            return WebhookIngestResult(status="duplicate", duplicate=True)

        operation = TOPIC_TO_OPERATION.get(normalized)
        if operation is None or tenant is None:
            reason = "no handler for this topic" if operation is None else "no tenant for this shop"
            self.webhooks.mark_skipped(webhook_event, f"{reason}: {shop_domain}")
            self.db.commit()
            logger.info("webhook.stored_without_job", {"topic": normalized, "shop": shop_domain, "reason": reason})
            return WebhookIngestResult(status="stored", webhook_event_id=webhook_event.id)

        job_payload: dict[str, Any] = dict(payload or {})
        if webhook_context:
            job_payload["webhook_context"] = webhook_context

        job = self.jobs.enqueue(
            tenant_id=tenant.id,
            operation=operation,
            topic=normalized,
            dedupe_key=_dedupe_key(operation, payload),
            shopify_webhook_id=shopify_webhook_id,
            webhook_event_id=webhook_event.id,
            payload=job_payload or None,
        )
        self.db.commit()
        logger.info("webhook.ingested", {"topic": normalized, "jobId": str(job.id)})
        return WebhookIngestResult(status="accepted", job_id=job.id, webhook_event_id=webhook_event.id)
