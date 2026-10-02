"""Demo events for the UAT App (App Store screenshots): a month of realistic
Server Events for every Market with an active pixel. Shoppers come in sessions
that follow the Standard Funnel, more in the evenings and at weekends, with
event IDs shaped like the storefront's. Almost all reached Meta; the latest
Purchases still wait for their order.

Every demo row carries ``payload.demo = true`` and nothing is sent to Meta, so
``--clear`` removes exactly what was seeded. Refused when APP_ENV is production.
The daily retention drops events after 30 days, so seed shortly before the
screenshots.

    docker exec afsmultipixel-api-uat python -m app.services.demo_events --shop <shop>.myshopify.com
    docker exec afsmultipixel-api-uat python -m app.services.demo_events --shop <shop>.myshopify.com --clear
"""

from __future__ import annotations

import argparse
import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import MarketPixel, ServerEvent, ServerEventSource, ServerEventStatus, Tenant

# Shoppers per hour of the day (store time), relative: quiet nights, a lunch bump
# and the evening peak.
HOURLY = [2, 1, 1, 1, 1, 2, 4, 6, 8, 9, 10, 11, 12, 11, 10, 10, 11, 13, 15, 17, 18, 16, 11, 6]
# Monday … Sunday.
WEEKDAY = [0.9, 0.95, 1.0, 1.0, 1.05, 1.25, 1.2]
# Each further Market gets a smaller share of the first one's traffic.
MARKET_SHARE = [1.0, 0.62, 0.41, 0.3, 0.22]
PRODUCTS = [(8812345670123 + i * 7919, price) for i, price in enumerate((24.9, 39.0, 18.5, 59.9, 32.0, 74.5, 12.9, 45.0))]
SENT_DETAIL = "events_received: 1"
BATCH = 2000


class DemoRefused(RuntimeError):
    """Demo events can't be seeded here; the message says why."""


def seed_demo_events(
    db: Session,
    tenant: Tenant,
    *,
    days: int = 30,
    sessions_per_day: int = 160,
    now: datetime | None = None,
    rng: random.Random | None = None,
    utc_offset_hours: int = 3,
) -> int:
    """Insert ``days`` of demo events ending at ``now``; returns how many."""
    if get_settings().app_env == "production":
        raise DemoRefused("Demo events are for the UAT App only, never production.")
    pixels = list(
        db.scalars(
            select(MarketPixel)
            .where(MarketPixel.tenant_id == tenant.id, MarketPixel.active.is_(True))
            .order_by(MarketPixel.created_at)
        )
    )
    if not pixels:
        raise DemoRefused("No Market has an active pixel. Configure one in the app first.")
    now = now or datetime.now(UTC)
    rng = rng or random.Random()
    builder = _Builder(tenant, now, rng)
    start = now - timedelta(days=days)
    for index, pixel in enumerate(pixels):
        share = MARKET_SHARE[min(index, len(MARKET_SHARE) - 1)]
        hour = start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        while hour <= now:
            local = hour + timedelta(hours=utc_offset_hours)
            progress = (hour - start) / (now - start)  # a store growing over the month
            expected = (
                sessions_per_day * share * (0.85 + 0.3 * progress) * WEEKDAY[local.weekday()]
                * HOURLY[local.hour] / sum(HOURLY) * rng.uniform(0.75, 1.25)
            )
            for _ in range(_poisson(rng, expected)):
                began = hour + timedelta(seconds=rng.uniform(0, 3600))
                if began < now - timedelta(minutes=2):
                    builder.session(pixel, began)
            hour += timedelta(hours=1)
    for chunk in range(0, len(builder.rows), BATCH):
        db.execute(insert(ServerEvent), builder.rows[chunk : chunk + BATCH])
    db.commit()
    return len(builder.rows)


def clear_demo_events(db: Session, tenant: Tenant) -> int:
    removed = db.execute(
        delete(ServerEvent).where(ServerEvent.tenant_id == tenant.id, ServerEvent.payload["demo"].astext == "true")
    ).rowcount
    db.commit()
    return int(removed or 0)


class _Builder:
    def __init__(self, tenant: Tenant, now: datetime, rng: random.Random) -> None:
        self.tenant, self.now, self.rng = tenant, now, rng
        self.rows: list[dict[str, Any]] = []
        self.order_number = 1001
        self.order_id = 18922956062998

    def session(self, pixel: MarketPixel, at: datetime) -> None:
        rng = self.rng
        cart: list[tuple[int, float]] = []
        for _ in range(min(7, 1 + int(rng.expovariate(0.7)))):
            self._add(pixel, "PageView", at, self._browser_id(at))
            at += timedelta(seconds=rng.uniform(8, 70))
        if rng.random() > 0.62:
            return
        for _ in range(1 + int(rng.expovariate(1.1))):
            product = rng.choice(PRODUCTS)
            self._add(pixel, "ViewContent", at, self._browser_id(at), product=product)
            at += timedelta(seconds=rng.uniform(20, 140))
            if rng.random() < 0.16:
                cart.append(product)
                self._add(pixel, "AddToCart", at, self._browser_id(at), product=product)
                at += timedelta(seconds=rng.uniform(10, 60))
        if not cart or rng.random() > 0.52:
            return
        self._add(pixel, "InitiateCheckout", at, self._checkout_id(), cart=cart)
        at += timedelta(seconds=rng.uniform(40, 180))
        if rng.random() > 0.74:
            return
        self._add(pixel, "AddPaymentInfo", at, self._checkout_id(), cart=cart)
        at += timedelta(seconds=rng.uniform(30, 120))
        if rng.random() > 0.83:
            return
        self.order_id += rng.randint(4000, 90000)
        # The order webhook joins the Purchase within seconds; the newest may still wait.
        waiting = self.now - at < timedelta(minutes=3)
        self._add(pixel, "Purchase", at, f"purchase-{self.order_id}", cart=cart, waiting=waiting,
                  order_number=str(self.order_number))
        self.order_number += 1

    def _add(self, pixel: MarketPixel, name: str, at: datetime, event_id: str, *, product=None, cart=None,
             waiting: bool = False, order_number: str | None = None) -> None:
        if at > self.now:
            return
        items = cart or ([product] if product else [])
        custom: dict[str, Any] = {}
        if items:
            custom = {
                "content_ids": [str(p[0]) for p in items],
                "content_type": "product_group",
                "currency": "EUR",
                "value": round(sum(p[1] for p in items), 2),
            }
        status = ServerEventStatus.WAITING if waiting else ServerEventStatus.SENT
        self.rows.append(
            {
                "id": uuid.uuid4(),
                "tenant_id": self.tenant.id,
                "source": ServerEventSource.WEBHOOK if name == "Purchase" else ServerEventSource.RELAY,
                "event_name": name,
                "event_id": event_id,
                "shopify_market_id": pixel.shopify_market_id,
                "pixel_id": pixel.pixel_id,
                "marketing_consent": True,
                "payload": {
                    "demo": True,
                    "event": {
                        "event_name": name,
                        "event_id": event_id,
                        "event_time": int(at.timestamp()),
                        "action_source": "website",
                        "user_data": {},
                        "custom_data": custom,
                    },
                },
                "status": status,
                "attempt_count": 0 if waiting else 1,
                "meta_response": {"detail": "Waiting for the order webhook" if waiting else SENT_DETAIL},
                "order_number": order_number,
                "created_at": at,
                "updated_at": at + timedelta(seconds=self.rng.uniform(1, 20)),
            }
        )

    def _browser_id(self, at: datetime) -> str:
        """The theme embed's ``mpx-<ms>-<8 base36>``."""
        alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
        return f"mpx-{int(at.timestamp() * 1000)}-{''.join(self.rng.choice(alphabet) for _ in range(8))}"

    def _checkout_id(self) -> str:
        """Checkout's Web Pixel event IDs as Shopify gives them: ``sh-fc1a7fc1-7728-4FE9-726C-BA2753014B0C``."""
        raw = f"{self.rng.getrandbits(128):032x}"
        return f"sh-{raw[:8]}-" + "-".join(part.upper() for part in (raw[8:12], raw[12:16], raw[16:20], raw[20:]))


def _poisson(rng: random.Random, mean: float) -> int:
    if mean <= 0:
        return 0
    count, total = 0, rng.expovariate(1.0)
    while total < mean:
        count += 1
        total += rng.expovariate(1.0)
    return count


def main() -> None:
    from app.db.session import SessionLocal
    from app.services.tenant_service import TenantService

    parser = argparse.ArgumentParser(description="Seed or clear demo events for App Store screenshots (UAT only).")
    parser.add_argument("--shop", required=True, help="The shop's myshopify domain")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--sessions-per-day", type=int, default=160, help="Shopper sessions a day in the first Market")
    parser.add_argument("--clear", action="store_true", help="Remove the demo events instead")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        tenant = TenantService(db).get_tenant_by_shop_domain(args.shop)
        if tenant is None:
            raise SystemExit(f"No shop {args.shop} in this database")
        if args.clear:
            print(f"Removed {clear_demo_events(db, tenant)} demo events")
        else:
            count = seed_demo_events(db, tenant, days=args.days, sessions_per_day=args.sessions_per_day)
            print(f"Seeded {count} demo events over {args.days} days")
    except DemoRefused as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        db.close()


if __name__ == "__main__":
    main()
