"""Relays and Server Events (spec §3.2): the Relay is decrypted, validated and
stored; the worker sends it to the Conversions API with retries, pauses a
Market whose token Meta rejects, and resumes it when the token is replaced."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import MarketPixel, ServerEvent, ServerEventStatus, TokenState
from app.services.relay_crypto import relay_key_pair
from app.services.relay_service import InMemoryRateLimiter, RelayContext, RelayService
from app.services.server_event_sender import MetaAnswer, ServerEventSender
from tests.test_markets import BG, GR, PIXEL, SHOP, TOKEN, _service, _tenant
from tests.test_publishing import CIPHER, browser_envelope

ORIGIN = "https://dontmiss.bg"
CTX = RelayContext(origin=ORIGIN, ip="203.0.113.7", user_agent="Mozilla/5.0 test")


def _shop(db, *, hosts=("dontmiss.bg", SHOP)):
    tenant = _tenant(db)
    tenant.storefront_hosts = list(hosts)
    tenant.storefront_hosts_synced_at = datetime.now(UTC)
    db.commit()
    service = _service(db, markets=(BG, GR))
    service.sync(tenant)
    service.save_pixel(tenant, 101, pixel_id=PIXEL, token=TOKEN, test_event_code="TEST1")
    return tenant


def _relay(**over) -> dict:
    payload = {
        "shop": SHOP,
        "event": "ViewContent",
        "eventId": "evt-1",
        "eventTime": int(datetime.now(UTC).timestamp() * 1000),
        "marketId": "101",
        "pixelId": PIXEL,
        "url": "https://dontmiss.bg/products/x",
        "fbp": "fb.1.1.2",
        "fbc": None,
        "customData": {"content_ids": ["7"], "content_type": "product_group", "value": 9.5, "currency": "EUR"},
    }
    payload.update(over)
    return payload


def _receive(db, payload=None, ctx=CTX, limiter=None) -> str:
    keys = relay_key_pair(db, CIPHER)
    body = browser_envelope(keys.public_key, payload or _relay())
    return RelayService(db, cipher=CIPHER, limiter=limiter or InMemoryRateLimiter()).receive(body, ctx)


def _events(db) -> list[ServerEvent]:
    return list(db.scalars(select(ServerEvent).order_by(ServerEvent.created_at)))


class FakeMetaApi:
    def __init__(self, *answers: MetaAnswer) -> None:
        self.answers = list(answers) or [MetaAnswer(status=200, body={"events_received": 1})]
        self.sent: list[tuple[str, dict]] = []

    def __call__(self, pixel_id: str, body: dict) -> MetaAnswer:
        self.sent.append((pixel_id, body))
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


def _sender(db, meta: FakeMetaApi, now: datetime | None = None) -> ServerEventSender:
    return ServerEventSender(db, post=meta, cipher=CIPHER, now=lambda: now or datetime.now(UTC))


# --- receiving -------------------------------------------------------------------------
@pytest.mark.integration
def test_a_valid_relay_is_stored_for_the_worker(db):
    _shop(db)

    assert _receive(db) == "stored"

    (event,) = _events(db)
    assert (event.event_name, event.event_id, event.shopify_market_id, event.pixel_id, event.status) == (
        "ViewContent", "evt-1", 101, PIXEL, ServerEventStatus.RECEIVED
    )
    meta_event = event.payload["event"]
    assert meta_event["user_data"] == {"client_ip_address": "203.0.113.7", "client_user_agent": "Mozilla/5.0 test",
                                       "fbp": "fb.1.1.2"}
    assert meta_event["custom_data"]["content_ids"] == ["7"]
    assert meta_event["action_source"] == "website"


@pytest.mark.integration
def test_garbage_is_rejected_and_stores_nothing(db):
    _shop(db)

    outcome = RelayService(db, cipher=CIPHER, limiter=InMemoryRateLimiter()).receive("garbage", CTX)

    assert outcome == "rejected"
    assert _events(db) == []


@pytest.mark.integration
def test_an_unknown_shop_is_rejected(db):
    _shop(db)

    assert _receive(db, _relay(shop="stranger.myshopify.com")) == "rejected"
    assert _events(db) == []


@pytest.mark.integration
def test_a_foreign_origin_is_rejected_and_logged(db):
    _shop(db)

    outcome = _receive(db, ctx=RelayContext(origin="https://evil.example", ip="1.2.3.4", user_agent="x"))

    assert outcome == "rejected"
    (event,) = _events(db)
    assert event.status == ServerEventStatus.REJECTED and "Origin" in event.meta_response["detail"]


@pytest.mark.integration
def test_the_web_pixels_null_origin_is_accepted(db):
    _shop(db)

    assert _receive(db, ctx=RelayContext(origin="null", ip="1.2.3.4", user_agent="x")) == "stored"


@pytest.mark.integration
def test_a_pair_that_isnt_in_the_mapping_is_rejected_and_logged(db):
    _shop(db)

    assert _receive(db, _relay(marketId="102")) == "rejected"
    assert _receive(db, _relay(eventId="evt-2", pixelId="9999999999999999")) == "rejected"

    assert [e.status for e in _events(db)] == [ServerEventStatus.REJECTED] * 2


@pytest.mark.integration
def test_relays_over_the_rate_limit_are_dropped(db):
    _shop(db)
    limiter = InMemoryRateLimiter(per_ip=2)

    outcomes = [_receive(db, _relay(eventId=f"e{i}"), limiter=limiter) for i in range(3)]

    assert outcomes == ["stored", "stored", "limited"]


@pytest.mark.integration
def test_an_uninstalled_shop_is_rejected(db):
    from app.services.tenant_service import TenantService

    _shop(db)
    TenantService(db).sync_shopify_uninstall(SHOP)

    assert _receive(db) == "rejected"


# --- sending ------------------------------------------------------------------------------
@pytest.mark.integration
def test_the_worker_sends_the_event_with_the_markets_token_and_test_code(db):
    _shop(db)
    _receive(db)
    meta = FakeMetaApi()

    assert _sender(db, meta).send_due() == 1

    ((pixel_id, body),) = meta.sent
    assert pixel_id == PIXEL
    assert body["access_token"] == TOKEN and body["test_event_code"] == "TEST1"
    assert body["data"][0]["event_id"] == "evt-1"
    (event,) = _events(db)
    assert event.status == ServerEventStatus.SENT
    assert event.payload["event"]["user_data"] == {}  # no personal data kept once sent


@pytest.mark.integration
def test_a_temporary_failure_retries_on_the_backoff_then_fails(db):
    _shop(db)
    _receive(db)
    meta = FakeMetaApi(MetaAnswer(status=503, body={"error": {"message": "busy"}}))
    start = datetime.now(UTC)

    delays = []
    now = start
    for _ in range(6):
        _sender(db, meta, now=now).send_due()
        (event,) = _events(db)
        db.refresh(event)
        if event.next_attempt_at is not None and event.status == ServerEventStatus.RECEIVED:
            delays.append(int((event.next_attempt_at - now).total_seconds()))
            now = event.next_attempt_at
    assert delays == [60, 300, 1800, 7200, 21600]
    assert event.status == ServerEventStatus.FAILED and event.attempt_count == 6


@pytest.mark.integration
def test_a_rejected_token_pauses_the_market_and_keeps_its_events(db):
    _shop(db)
    _receive(db, _relay(eventId="a"))
    _receive(db, _relay(eventId="b"))
    meta = FakeMetaApi(MetaAnswer(status=400, body={"error": {"type": "OAuthException", "code": 190,
                                                              "message": "Session has expired"}}))

    _sender(db, meta).send_due()

    assert len(meta.sent) == 1  # the second event isn't tried with a dead token
    assert {e.status for e in _events(db)} == {ServerEventStatus.PAUSED}
    pixel = db.scalar(select(MarketPixel))
    assert pixel.token_state == TokenState.REJECTED and "Session has expired" in pixel.token_error


@pytest.mark.integration
def test_replacing_the_token_resumes_paused_events_under_seven_days_old(db):
    tenant = _shop(db)
    _receive(db, _relay(eventId="fresh"))
    _receive(db, _relay(eventId="stale"))
    _sender(db, FakeMetaApi(MetaAnswer(status=400, body={"error": {"code": 190, "message": "expired"}}))).send_due()
    stale = db.scalar(select(ServerEvent).where(ServerEvent.event_id == "stale"))
    stale.created_at = datetime.now(UTC) - timedelta(days=8)
    db.commit()

    _service(db, markets=(BG, GR)).save_pixel(tenant, 101, pixel_id=PIXEL, token=TOKEN + "new")
    meta = FakeMetaApi()
    _sender(db, meta).send_due()

    statuses = {e.event_id: e.status for e in _events(db)}
    assert statuses == {"fresh": ServerEventStatus.SENT, "stale": ServerEventStatus.FAILED}
    assert meta.sent[0][1]["access_token"] == TOKEN + "new"
    assert db.scalar(select(MarketPixel)).token_error is None


@pytest.mark.integration
def test_a_permanent_meta_error_marks_the_event_rejected_without_retry(db):
    _shop(db)
    _receive(db)

    _sender(db, FakeMetaApi(MetaAnswer(status=400, body={"error": {"code": 100, "message": "Invalid parameter"}}))).send_due()

    (event,) = _events(db)
    assert event.status == ServerEventStatus.REJECTED and event.next_attempt_at is None
    assert "Invalid parameter" in event.meta_response["detail"]


@pytest.mark.integration
def test_an_event_for_a_market_unmapped_since_is_skipped(db):
    tenant = _shop(db)
    _receive(db)
    _service(db, markets=(BG, GR)).remove_pixel(tenant, 101)
    meta = FakeMetaApi()

    _sender(db, meta).send_due()

    assert meta.sent == []
    assert _events(db)[0].status == ServerEventStatus.SKIPPED


# --- what the page shows -------------------------------------------------------------------------
@pytest.mark.integration
def test_stats_count_browser_and_server_events_per_market(db):
    from app.services.event_stats import market_stats

    tenant = _shop(db)
    _receive(db, _relay(eventId="1"))
    _receive(db, _relay(eventId="2"))
    _receive(db, _relay(eventId="3", marketId="102"))  # rejected: not mapped
    _sender(db, FakeMetaApi(MetaAnswer(status=200, body={}), MetaAnswer(status=503, body={}))).send_due()

    stats = market_stats(db, tenant)

    bg = stats.markets[101]
    assert (bg.browser, bg.server, bg.purchases) == (2, 1, 0)
    assert len(bg.series) == 24 and sum(bg.series) == 2
    assert bg.last_event_at is not None
    assert (stats.browser_24h, stats.server_24h) == (2, 1)


@pytest.mark.integration
def test_the_event_log_lists_recent_events_newest_first(db):
    from app.services.event_stats import event_log

    tenant = _shop(db)
    _receive(db, _relay(eventId="1"))
    _receive(db, _relay(eventId="2", marketId="102"))

    rows = event_log(db, tenant)
    assert [(r.event_id, r.status, r.sent_as) for r in rows] == [("2", "rejected", "Relay"), ("1", "received", "Server")]
    assert [r.event_id for r in event_log(db, tenant, market_id=101)] == ["1"]


@pytest.mark.integration
def test_one_broken_event_doesnt_block_the_queue(db):
    _shop(db)
    _receive(db, _relay(eventId="broken"))
    _receive(db, _relay(eventId="fine"))
    broken = db.scalar(select(ServerEvent).where(ServerEvent.event_id == "broken"))
    broken.payload = None  # e.g. a row damaged by hand
    db.commit()

    _sender(db, FakeMetaApi()).send_due()

    statuses = {e.event_id: e.status for e in _events(db)}
    assert statuses == {"broken": ServerEventStatus.FAILED, "fine": ServerEventStatus.SENT}


@pytest.mark.integration
def test_a_foreign_origin_is_rejected_even_before_the_first_host_sync(db):
    tenant = _shop(db)
    tenant.storefront_hosts_synced_at = None
    tenant.storefront_hosts = []
    db.commit()

    assert _receive(db, ctx=RelayContext(origin="https://evil.example", ip="1.2.3.4", user_agent="x")) == "rejected"


@pytest.mark.integration
def test_resaving_with_the_stored_token_also_resumes_paused_events(db):
    # The merchant fixed the token's permissions in Meta and saved again.
    tenant = _shop(db)
    _receive(db)
    _sender(db, FakeMetaApi(MetaAnswer(status=400, body={"error": {"code": 190, "message": "x"}}))).send_due()
    pixel = db.scalar(select(MarketPixel))
    pixel.token_state = TokenState.OK  # what a passing re-check leads to
    db.commit()

    _service(db, markets=(BG, GR)).save_pixel(tenant, 101, pixel_id=PIXEL, token=None)

    assert _events(db)[0].status == ServerEventStatus.RECEIVED
