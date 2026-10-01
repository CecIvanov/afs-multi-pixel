"""Daily retention (spec §6, §8): Server Events (the event log) are kept 30 days;
unmatched pending Purchases and paused events expire after Meta's 7 days."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import ServerEvent
from app.services.purchase_join import expire_pending_purchases
from app.services.server_event_sender import expire_paused

logger = get_logger().child({"component": "retention"})

SERVER_EVENT_RETENTION = timedelta(days=30)


def run_daily_retention(db: Session, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    deleted = db.execute(delete(ServerEvent).where(ServerEvent.created_at < now - SERVER_EVENT_RETENTION)).rowcount
    db.commit()
    result = {
        "server_events_deleted": int(deleted or 0),
        "pending_purchases_expired": expire_pending_purchases(db, now),
        "paused_expired": expire_paused(db, now),
    }
    logger.info("retention.daily.completed", result)
    return result
