from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import WebhookEvent, WebhookEventStatus


class WebhookEventService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record_received(
        self,
        *,
        shopify_webhook_id: str,
        topic: str,
        tenant_id: uuid.UUID | None = None,
        payload: dict | None = None,
    ) -> WebhookEvent | None:
        """Insert the webhook id for delivery-level dedup. Returns None on duplicate
        (unique constraint on shopify_webhook_id)."""
        event = WebhookEvent(
            tenant_id=tenant_id,
            topic=topic,
            shopify_webhook_id=shopify_webhook_id,
            payload=payload or {},
            status=WebhookEventStatus.RECEIVED,
        )
        self.db.add(event)
        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            return None
        return event

    def mark_processed(self, event: WebhookEvent) -> None:
        event.status = WebhookEventStatus.PROCESSED
        event.processed_at = datetime.now(UTC)
        self.db.add(event)
        self.db.commit()

    def mark_failed(self, event: WebhookEvent, message: str) -> None:
        event.status = WebhookEventStatus.FAILED
        event.error_message = message
        self.db.add(event)
        self.db.commit()

    def purge_retention(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(hours=get_settings().webhook_events_retention_hours)
        result = self.db.execute(delete(WebhookEvent).where(WebhookEvent.created_at < cutoff))
        self.db.commit()
        return int(result.rowcount or 0)
