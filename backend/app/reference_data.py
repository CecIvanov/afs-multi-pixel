from __future__ import annotations

from datetime import UTC, datetime, timedelta


def default_subscription_period(now: datetime | None = None) -> tuple[datetime, datetime]:
    """A 30-day default billing period starting now. Phase 3 replaces this with the
    real cycle read from the Shopify Partner API."""
    start = now or datetime.now(UTC)
    return start, start + timedelta(days=30)
