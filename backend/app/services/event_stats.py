"""What the Market health page shows (spec §4): per-Market counts and a 24-hour
events-per-hour series, the summary row, and the event log. Every Server Event
row stands for one Browser Event the storefront sent and relayed."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ServerEvent, ServerEventStatus, Tenant
from app.services.server_event_sender import META_EVENT_MAX_AGE

WINDOW = timedelta(hours=24)
EVENT_LOG_LIMIT = 200


@dataclass
class MarketStats:
    browser: int = 0
    server: int = 0
    purchases: int = 0
    series: list[int] = field(default_factory=lambda: [0] * 24)
    last_event_at: datetime | None = None
    # Server Events on hold for a working token, of any age, and when the oldest
    # passes Meta's 7-day limit and is dropped.
    held: int = 0
    held_until: datetime | None = None


@dataclass
class Stats:
    markets: dict[int, MarketStats]
    browser_24h: int
    server_24h: int


def market_stats(db: Session, tenant: Tenant, now: datetime | None = None) -> Stats:
    now = now or datetime.now(UTC)
    since = now - WINDOW
    rows = db.execute(
        select(ServerEvent.shopify_market_id, ServerEvent.event_name, ServerEvent.status, ServerEvent.created_at).where(
            ServerEvent.tenant_id == tenant.id,
            ServerEvent.created_at >= since,
            ServerEvent.status != ServerEventStatus.REJECTED,
        )
    ).all()
    markets: dict[int, MarketStats] = {}
    for market_id, name, status, created_at in rows:
        m = markets.setdefault(market_id, MarketStats())
        m.browser += 1
        m.server += status == ServerEventStatus.SENT
        m.purchases += name == "Purchase"
        hour = min(23, max(0, int((created_at - since).total_seconds() // 3600)))
        m.series[hour] += 1
        if m.last_event_at is None or created_at > m.last_event_at:
            m.last_event_at = created_at
    held = db.execute(
        select(ServerEvent.shopify_market_id, func.count(), func.min(ServerEvent.created_at))
        .where(ServerEvent.tenant_id == tenant.id, ServerEvent.status == ServerEventStatus.PAUSED)
        .group_by(ServerEvent.shopify_market_id)
    ).all()
    for market_id, count, oldest in held:
        m = markets.setdefault(market_id, MarketStats())
        m.held = int(count)
        m.held_until = oldest + META_EVENT_MAX_AGE
    return Stats(
        markets=markets,
        browser_24h=sum(m.browser for m in markets.values()),
        server_24h=sum(m.server for m in markets.values()),
    )


@dataclass(frozen=True)
class EventLogRow:
    created_at: datetime
    event_name: str
    event_id: str
    shopify_market_id: int
    sent_as: str  # "Server" for events the backend handled, "Relay" for refused Relays
    status: str
    detail: str | None


def event_log(
    db: Session, tenant: Tenant, *, market_id: int | None = None, limit: int = EVENT_LOG_LIMIT
) -> list[EventLogRow]:
    query = select(ServerEvent).where(ServerEvent.tenant_id == tenant.id)
    if market_id is not None:
        query = query.where(ServerEvent.shopify_market_id == market_id)
    events = db.scalars(query.order_by(ServerEvent.created_at.desc(), ServerEvent.id.desc()).limit(limit)).all()
    return [
        EventLogRow(
            created_at=e.created_at,
            event_name=e.event_name,
            event_id=e.event_id,
            shopify_market_id=e.shopify_market_id,
            sent_as="Relay" if e.status == ServerEventStatus.REJECTED else "Server",
            status=e.status.value,
            detail=(e.meta_response or {}).get("detail"),
        )
        for e in events
    ]
