"""The Market page (#15): deactivating and reactivating a Market Pixel, the stored
result of Check with Meta, per-Market stats for 24 h / 7 d / 30 d, and the event
table's filters, search and paging."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import MarketPixel, ServerEvent, ServerEventStatus, TokenState
from app.services.market_service import PixelCheck
from app.services.server_event_sender import MetaAnswer, expire_paused
from tests.test_markets import BG, GR, PIXEL, TOKEN, FakeMeta, _service
from tests.test_publishing import FakeAdmin, _publisher
from tests.test_relay import FakeMetaApi, _events, _receive, _relay, _sender, _shop

TOKEN_REJECTED = MetaAnswer(status=400, body={"error": {"code": 190, "message": "expired"}})


def _pixel(db) -> MarketPixel:
    return db.scalar(select(MarketPixel).where(MarketPixel.shopify_market_id == 101))


def _statuses(db) -> dict[str, ServerEventStatus]:
    return {e.event_id: e.status for e in _events(db)}


# --- deactivate / reactivate -------------------------------------------------------------
@pytest.mark.integration
def test_deactivating_keeps_the_pixel_and_token(db):
    tenant = _shop(db)

    view = _service(db).deactivate(tenant, 101)

    pixel = _pixel(db)
    assert (pixel.active, pixel.pixel_id, bool(pixel.capi_token_encrypted)) == (False, PIXEL, True)
    assert view.pixel.active is False


@pytest.mark.integration
def test_a_deactivated_pixel_is_left_out_of_the_storefront_mapping(db):
    tenant = _shop(db)
    service = _service(db, markets=(BG, GR))
    service.save_pixel(tenant, 102, pixel_id="2222", token=TOKEN)
    service.deactivate(tenant, 101)
    admin = FakeAdmin()

    _publisher(db, admin).publish(tenant)

    (metafield,) = admin.variables_of("metafieldsSet")["metafields"]
    assert json.loads(metafield["value"])["pixels"] == {"102": "2222"}


@pytest.mark.integration
def test_relays_for_a_deactivated_market_are_refused(db):
    tenant = _shop(db)
    _service(db).deactivate(tenant, 101)

    assert _receive(db, _relay(eventId="late")) == "rejected"
    assert _statuses(db) == {"late": ServerEventStatus.REJECTED}


@pytest.mark.integration
def test_deactivating_holds_the_events_still_queued(db):
    tenant = _shop(db)
    _receive(db, _relay(eventId="queued"))

    _service(db).deactivate(tenant, 101)
    meta = FakeMetaApi()
    _sender(db, meta).send_due()

    assert meta.sent == []
    assert _statuses(db) == {"queued": ServerEventStatus.PAUSED}


@pytest.mark.integration
def test_reactivating_sends_the_held_events_when_the_token_works(db):
    tenant = _shop(db)
    _receive(db, _relay(eventId="queued"))
    service = _service(db)
    service.deactivate(tenant, 101)

    view = service.reactivate(tenant, 101)
    _sender(db, FakeMetaApi()).send_due()

    assert view.pixel.active is True
    assert _statuses(db) == {"queued": ServerEventStatus.SENT}


@pytest.mark.integration
def test_reactivating_checks_the_token_and_keeps_events_held_if_meta_refuses_it(db):
    tenant = _shop(db)
    _receive(db, _relay(eventId="a"))
    _service(db).deactivate(tenant, 101)
    refused = FakeMeta(PixelCheck(ok=False, error="Meta refused the check: expired"))

    view = _service(db, meta=refused).reactivate(tenant, 101)

    assert refused.calls == [(PIXEL, TOKEN)]
    assert view.pixel.active is True
    assert (view.pixel.token_state, view.pixel.token_error) == ("rejected", "Meta refused the check: expired")
    assert _statuses(db) == {"a": ServerEventStatus.PAUSED}


@pytest.mark.integration
def test_held_events_of_a_deactivated_market_still_drop_after_seven_days(db):
    tenant = _shop(db)
    _receive(db, _relay(eventId="old"))
    _service(db).deactivate(tenant, 101)
    _events(db)[0].created_at = datetime.now(UTC) - timedelta(days=8)
    db.commit()

    expire_paused(db)

    assert _statuses(db) == {"old": ServerEventStatus.FAILED}


@pytest.mark.integration
def test_deactivating_a_market_without_a_pixel_is_refused(db):
    tenant = _shop(db)

    with pytest.raises(LookupError):
        _service(db).deactivate(tenant, 102)


# --- the connection panel -----------------------------------------------------------------
@pytest.mark.integration
def test_the_view_shows_the_tokens_last_four_characters_and_the_last_check(db):
    tenant = _shop(db)

    pixel = _service(db).list_markets(tenant)[0].pixel

    assert pixel.token_hint == TOKEN[-4:]
    assert pixel.last_check_ok is True
    assert pixel.last_checked_at is not None
    assert pixel.active is True


@pytest.mark.integration
def test_rechecking_the_saved_pair_stores_metas_answer(db):
    tenant = _shop(db)
    meta = FakeMeta(PixelCheck(ok=False, error="This token can't send to this pixel."))

    check = _service(db, meta=meta).recheck(tenant, 101)

    assert check.ok is False
    assert meta.calls == [(PIXEL, TOKEN)]
    pixel = _pixel(db)
    assert (pixel.last_check_ok, pixel.last_check_error) == (False, "This token can't send to this pixel.")


@pytest.mark.integration
def test_a_passing_recheck_clears_a_rejected_token_and_sends_the_held_events(db):
    # Meta can take a few minutes to allow a newly connected dataset.
    tenant = _shop(db)
    _receive(db, _relay(eventId="a"))
    _sender(db, FakeMetaApi(TOKEN_REJECTED)).send_due()
    assert _pixel(db).token_state == TokenState.REJECTED

    _service(db).recheck(tenant, 101)
    _sender(db, FakeMetaApi()).send_due()

    assert _pixel(db).token_state == TokenState.OK
    assert _statuses(db) == {"a": ServerEventStatus.SENT}


# --- stats by range --------------------------------------------------------------------------
def _age(db, event_id: str, **delta) -> None:
    event = db.scalar(select(ServerEvent).where(ServerEvent.event_id == event_id))
    event.created_at = datetime.now(UTC) - timedelta(**delta)
    db.commit()


@pytest.mark.integration
def test_market_detail_counts_totals_and_types_for_the_range(db):
    from app.services.event_stats import market_detail

    tenant = _shop(db)
    for event_id, name in [("1", "PageView"), ("2", "PageView"), ("3", "ViewContent"), ("4", "PageView")]:
        _receive(db, _relay(eventId=event_id, event=name))
    _sender(db, FakeMetaApi(MetaAnswer(status=200), MetaAnswer(status=200), MetaAnswer(status=503))).send_due()
    _age(db, "4", days=3)  # outside 24 h, inside 7 d

    day = market_detail(db, tenant, 101, "24h")
    week = market_detail(db, tenant, 101, "7d")

    assert (day.browser, day.sent, day.not_sent) == (3, 2, 1)
    assert [(t.event_name, t.count, t.sent) for t in day.types] == [("PageView", 2, 2), ("ViewContent", 1, 0)]
    assert week.browser == 4
    assert [(t.event_name, t.count) for t in week.types] == [("PageView", 3), ("ViewContent", 1)]


@pytest.mark.integration
def test_market_detail_series_is_hourly_for_a_day_and_daily_otherwise(db):
    from app.services.event_stats import market_detail

    tenant = _shop(db)
    _receive(db, _relay(eventId="now"))
    _receive(db, _relay(eventId="old"))
    _age(db, "old", days=20)

    day = market_detail(db, tenant, 101, "24h")
    month = market_detail(db, tenant, 101, "30d")

    assert len(day.series) == 24 and day.series[-1].not_sent == 1
    assert len(month.series) == 30 and sum(b.not_sent for b in month.series) == 2
    assert len(market_detail(db, tenant, 101, "7d").series) == 7


@pytest.mark.integration
def test_market_detail_splits_held_from_other_unsent_events(db):
    from app.services.event_stats import market_detail

    tenant = _shop(db)
    _receive(db, _relay(eventId="a"))
    _receive(db, _relay(eventId="b"))
    _sender(db, FakeMetaApi(TOKEN_REJECTED)).send_due()
    _receive(db, _relay(eventId="c", marketId="101", pixelId="999"))  # refused: wrong pixel

    detail = market_detail(db, tenant, 101, "24h")

    assert (detail.held, detail.not_sent, detail.rejected) == (2, 2, 1)
    assert sum(b.held for b in detail.series) == 2


@pytest.mark.integration
def test_market_detail_counts_purchases_sent_with_customer_data(db):
    from app.services.event_stats import market_detail

    tenant = _shop(db)
    for event_id, status in [("purchase-1", ServerEventStatus.SENT), ("purchase-2", ServerEventStatus.WAITING)]:
        _receive(db, _relay(eventId=event_id))
        row = db.scalar(select(ServerEvent).where(ServerEvent.event_id == event_id))
        row.event_name, row.status = "Purchase", status
    db.commit()

    detail = market_detail(db, tenant, 101, "24h")

    assert (detail.purchases, detail.purchases_sent) == (2, 1)


@pytest.mark.integration
def test_an_unknown_range_is_refused(db):
    from app.services.event_stats import market_detail

    tenant = _shop(db)
    with pytest.raises(ValueError):
        market_detail(db, tenant, 101, "1y")


# --- the event table --------------------------------------------------------------------------
@pytest.mark.integration
def test_the_event_page_filters_by_event_and_status_with_counts(db):
    from app.services.event_stats import event_page

    tenant = _shop(db)
    for event_id, name in [("pv-1", "PageView"), ("pv-2", "PageView"), ("vc-1", "ViewContent")]:
        _receive(db, _relay(eventId=event_id, event=name))
    _sender(db, FakeMetaApi(MetaAnswer(status=200), MetaAnswer(status=503))).send_due()

    page = event_page(db, tenant, 101, range_key="24h", event_name="PageView", status="sent")

    assert [r.event_id for r in page.rows] == ["pv-1"]
    assert page.total == 1
    assert page.event_counts == {"PageView": 2, "ViewContent": 1}
    assert page.status_counts == {"sent": 1, "waiting": 1}


@pytest.mark.integration
def test_held_is_the_paused_status_and_waiting_covers_queued_events(db):
    from app.services.event_stats import event_page

    tenant = _shop(db)
    _receive(db, _relay(eventId="a"))
    _sender(db, FakeMetaApi(TOKEN_REJECTED)).send_due()
    _receive(db, _relay(eventId="b"))  # stored straight as paused: the token is rejected

    page = event_page(db, tenant, 101, range_key="24h", status="held")

    assert {r.event_id for r in page.rows} == {"a", "b"}
    assert {r.status for r in page.rows} == {"held"}


@pytest.mark.integration
def test_the_event_page_searches_by_event_id_or_order_number(db):
    from app.services.event_stats import event_page

    tenant = _shop(db)
    _receive(db, _relay(eventId="purchase-6390114"))
    _receive(db, _relay(eventId="mpx-abc"))

    assert [r.event_id for r in event_page(db, tenant, 101, range_key="24h", search="6390114").rows] == [
        "purchase-6390114"
    ]


@pytest.mark.integration
def test_the_event_page_pages_newest_first(db):
    from app.services.event_stats import event_page

    tenant = _shop(db)
    for i in range(5):
        _receive(db, _relay(eventId=f"e{i}"))
        _age(db, f"e{i}", minutes=10 - i)

    first = event_page(db, tenant, 101, range_key="24h", page=1, page_size=2)
    last = event_page(db, tenant, 101, range_key="24h", page=3, page_size=2)

    assert [r.event_id for r in first.rows] == ["e4", "e3"]
    assert [r.event_id for r in last.rows] == ["e0"]
    assert (first.total, first.page, first.page_size) == (5, 1, 2)


@pytest.mark.integration
def test_the_event_page_finds_a_purchase_by_its_order_number(db):
    from app.services.event_stats import event_page
    from app.services.purchase_join import PurchaseJoin

    tenant = _shop(db)
    _receive(db, _relay(event="Purchase", eventId="purchase-5551234", orderId="5551234",
                        customData={"content_ids": ["7"], "value": 30, "currency": "EUR", "order_id": "5551234"}))
    PurchaseJoin(db).record_order(tenant, {"id": 5551234, "order_number": 1001, "name": "#1001", "email": "a@b.c"})
    _receive(db, _relay(eventId="mpx-1001x"))

    for search in ("#1001", "1001"):
        rows = event_page(db, tenant, 101, search=search).rows
        assert "purchase-5551234" in [r.event_id for r in rows]
    assert [r.event_id for r in event_page(db, tenant, 101, search="#1001").rows] == ["purchase-5551234"]
