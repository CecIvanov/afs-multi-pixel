"""What the Markets pages show (spec §4, #15): per-Market 24-hour counts and
events-per-hour series and the summary row for the overview; one Market's
figures for 24 h / 7 d / 30 d and its event table for the Market page. Every Server Event
row stands for one Browser Event the storefront sent and relayed."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import ServerEvent, ServerEventStatus, Tenant
from app.services.server_event_sender import META_EVENT_MAX_AGE

WINDOW = timedelta(hours=24)


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


# The Market page's ranges: how far back, and the chart's bucket size.
RANGES: dict[str, tuple[timedelta, timedelta]] = {
    "24h": (timedelta(hours=24), timedelta(hours=1)),
    "7d": (timedelta(days=7), timedelta(days=1)),
    "30d": (timedelta(days=30), timedelta(days=1)),
}
# The statuses the merchant sees. ``paused`` is shown as Held everywhere.
DISPLAY_STATUS: dict[ServerEventStatus, str] = {
    ServerEventStatus.SENT: "sent",
    ServerEventStatus.PAUSED: "held",
    ServerEventStatus.RECEIVED: "waiting",
    ServerEventStatus.WAITING: "waiting",
    ServerEventStatus.REJECTED: "rejected",
    ServerEventStatus.FAILED: "failed",
    ServerEventStatus.SKIPPED: "skipped",
}
FUNNEL_ORDER = ("PageView", "ViewContent", "Search", "AddToCart", "InitiateCheckout", "AddPaymentInfo", "Purchase")
EVENT_PAGE_SIZE = 50


def _window(range_key: str, now: datetime) -> tuple[datetime, timedelta, int]:
    if range_key not in RANGES:
        raise ValueError(f"Unknown range {range_key!r}")
    span, step = RANGES[range_key]
    return now - span, step, int(span / step)


@dataclass
class TypeCount:
    event_name: str
    count: int = 0
    sent: int = 0


@dataclass
class Bucket:
    sent: int = 0
    held: int = 0
    not_sent: int = 0  # neither sent nor held: waiting, failed or skipped


@dataclass
class MarketDetail:
    """One Market's figures for a range. ``browser`` counts every event the storefront
    relayed and the backend accepted; refused Relays are ``rejected``."""

    range: str
    browser: int = 0
    sent: int = 0
    purchases: int = 0
    # Purchases go to Meta only once orders/create adds the hashed customer data.
    purchases_sent: int = 0
    not_sent: int = 0
    held: int = 0
    rejected: int = 0
    types: list[TypeCount] = field(default_factory=list)
    series: list[Bucket] = field(default_factory=list)


def market_detail(
    db: Session, tenant: Tenant, market_id: int, range_key: str, now: datetime | None = None
) -> MarketDetail:
    now = now or datetime.now(UTC)
    since, step, buckets = _window(range_key, now)
    rows = db.execute(
        select(ServerEvent.event_name, ServerEvent.status, ServerEvent.created_at).where(
            ServerEvent.tenant_id == tenant.id,
            ServerEvent.shopify_market_id == market_id,
            ServerEvent.created_at >= since,
        )
    ).all()
    detail = MarketDetail(range=range_key, series=[Bucket() for _ in range(buckets)])
    types: dict[str, TypeCount] = {}
    for name, status, created_at in rows:
        if status == ServerEventStatus.REJECTED:
            detail.rejected += 1
            continue
        sent = status == ServerEventStatus.SENT
        held = status == ServerEventStatus.PAUSED
        detail.browser += 1
        detail.sent += sent
        detail.held += held
        detail.purchases += name == "Purchase"
        detail.purchases_sent += name == "Purchase" and sent
        type_count = types.setdefault(name, TypeCount(name))
        type_count.count += 1
        type_count.sent += sent
        bucket = detail.series[min(buckets - 1, max(0, int((created_at - since) / step)))]
        if sent:
            bucket.sent += 1
        elif held:
            bucket.held += 1
        else:
            bucket.not_sent += 1
    detail.not_sent = detail.browser - detail.sent
    funnel = {name: i for i, name in enumerate(FUNNEL_ORDER)}
    detail.types = sorted(types.values(), key=lambda t: (funnel.get(t.event_name, len(funnel)), t.event_name))
    return detail


@dataclass(frozen=True)
class EventRow:
    created_at: datetime
    event_name: str
    event_id: str
    sent_as: str  # "Server" for events the backend handled, "Relay" for refused Relays
    status: str  # a DISPLAY_STATUS value
    detail: str | None


@dataclass
class EventPage:
    rows: list[EventRow]
    total: int
    page: int
    page_size: int
    event_counts: dict[str, int]
    status_counts: dict[str, int]


def event_page(
    db: Session,
    tenant: Tenant,
    market_id: int,
    *,
    range_key: str = "24h",
    event_name: str | None = None,
    status: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = EVENT_PAGE_SIZE,
    now: datetime | None = None,
) -> EventPage:
    """The Market page's event table (the log keeps 30 days), newest first. The
    counts drive the filter chips: per event name without the event filter, per
    status with it."""
    now = now or datetime.now(UTC)
    since, _, _ = _window(range_key, now)
    scope = [
        ServerEvent.tenant_id == tenant.id,
        ServerEvent.shopify_market_id == market_id,
        ServerEvent.created_at >= since,
    ]
    search = (search or "").strip()
    if search.startswith("#"):
        # "#1001" is an order number as Shopify shows it.
        scope.append(ServerEvent.order_number == search.lstrip("#"))
    elif search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        scope.append(or_(ServerEvent.event_id.ilike(f"%{escaped}%", escape="\\"), ServerEvent.order_number == search))
    event_counts = dict(
        db.execute(select(ServerEvent.event_name, func.count()).where(*scope).group_by(ServerEvent.event_name)).all()
    )
    if event_name:
        scope.append(ServerEvent.event_name == event_name)
    status_counts: dict[str, int] = {}
    for raw, count in db.execute(select(ServerEvent.status, func.count()).where(*scope).group_by(ServerEvent.status)):
        key = DISPLAY_STATUS[raw]
        status_counts[key] = status_counts.get(key, 0) + int(count)
    if status:
        scope.append(ServerEvent.status.in_([raw for raw, key in DISPLAY_STATUS.items() if key == status]))
    total = db.scalar(select(func.count()).select_from(ServerEvent).where(*scope)) or 0
    page = max(1, page)
    events = db.scalars(
        select(ServerEvent)
        .where(*scope)
        .order_by(ServerEvent.created_at.desc(), ServerEvent.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    rows = [
        EventRow(
            created_at=e.created_at,
            event_name=e.event_name,
            event_id=e.event_id,
            sent_as="Relay" if e.status == ServerEventStatus.REJECTED else "Server",
            status=DISPLAY_STATUS[e.status],
            detail=(e.meta_response or {}).get("detail"),
        )
        for e in events
    ]
    return EventPage(
        rows=rows,
        total=int(total),
        page=page,
        page_size=page_size,
        event_counts={k: int(v) for k, v in event_counts.items()},
        status_counts=status_counts,
    )
