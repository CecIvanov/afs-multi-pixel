"""Demo events for the UAT App's App Store screenshots: a month of realistic
Server Events for the Markets that have an active pixel, removable again."""

from __future__ import annotations

import random
import re
from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import ServerEvent, ServerEventStatus
from app.services.demo_events import DemoRefused, clear_demo_events, seed_demo_events
from tests.test_markets import PIXEL, TOKEN, _service
from tests.test_relay import _receive, _relay, _shop

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


def _seed(db, tenant, **kw):
    return seed_demo_events(db, tenant, days=30, now=NOW, rng=random.Random(7), sessions_per_day=40, **kw)


def _events(db) -> list[ServerEvent]:
    return list(db.scalars(select(ServerEvent)))


@pytest.mark.integration
def test_demo_events_cover_the_month_for_markets_with_an_active_pixel(db):
    tenant = _shop(db)  # Bulgaria (101) has a pixel, Greece (102) none
    _service(db).save_pixel(tenant, 102, pixel_id="2222", token=TOKEN)
    _service(db).deactivate(tenant, 102)

    count = _seed(db, tenant)

    events = _events(db)
    assert count == len(events) > 1000
    assert {e.shopify_market_id for e in events} == {101}
    assert {e.pixel_id for e in events} == {PIXEL}
    assert min(e.created_at for e in events) >= NOW - timedelta(days=30)
    assert max(e.created_at for e in events) <= NOW
    days = {e.created_at.date() for e in events}
    assert len(days) >= 30


@pytest.mark.integration
def test_demo_events_follow_the_funnel_and_mostly_reach_meta(db):
    tenant = _shop(db)

    _seed(db, tenant)

    events = _events(db)
    names = Counter(e.event_name for e in events)
    funnel = ["PageView", "ViewContent", "AddToCart", "InitiateCheckout", "AddPaymentInfo", "Purchase"]
    assert [names[n] for n in funnel] == sorted((names[n] for n in funnel), reverse=True)
    assert names["Purchase"] > 0
    sent = [e for e in events if e.status == ServerEventStatus.SENT]
    assert len(sent) / len(events) > 0.95
    assert {e.meta_response["detail"] for e in sent} == {"events_received: 1"}


@pytest.mark.integration
def test_demo_event_ids_look_like_the_storefronts(db):
    tenant = _shop(db)

    _seed(db, tenant)

    for event in _events(db):
        if event.event_name == "Purchase":
            assert re.fullmatch(r"purchase-\d{14}", event.event_id)
            assert event.order_number and event.order_number.isdigit()
        elif event.event_name in ("InitiateCheckout", "AddPaymentInfo"):
            assert re.fullmatch(r"sh-[0-9a-f]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}", event.event_id)
        else:
            assert re.fullmatch(r"mpx-\d{13}-[0-9a-z]{8}", event.event_id)


@pytest.mark.integration
def test_clearing_removes_only_demo_events(db):
    tenant = _shop(db)
    _receive(db, _relay(eventId="real-1"))
    _seed(db, tenant)

    removed = clear_demo_events(db, tenant)

    assert removed > 1000
    assert [e.event_id for e in _events(db)] == ["real-1"]


@pytest.mark.integration
def test_demo_events_are_refused_in_production(db, monkeypatch):
    from app.config import get_settings

    tenant = _shop(db)
    monkeypatch.setattr(get_settings(), "app_env", "production")

    with pytest.raises(DemoRefused):
        _seed(db, tenant)
    assert _events(db) == []


@pytest.mark.integration
def test_a_shop_without_an_active_pixel_is_refused(db):
    tenant = _shop(db)
    _service(db).deactivate(tenant, 101)

    with pytest.raises(DemoRefused):
        _seed(db, tenant)
