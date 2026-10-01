"""Daily retention (spec §6, §8): Server Events older than 30 days are deleted,
unmatched pending Purchases and paused events past Meta's 7 days expire."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import PendingPurchase, ServerEvent, ServerEventStatus
from app.services.retention_service import run_daily_retention
from tests.test_purchase_join import _browser_purchase
from tests.test_relay import FakeMetaApi, _receive, _relay, _sender, _shop
from app.services.server_event_sender import MetaAnswer


def _age(db, model, days, **where):
    for row in db.scalars(select(model).filter_by(**where)):
        row.created_at = datetime.now(UTC) - timedelta(days=days)
    db.commit()


@pytest.mark.integration
def test_daily_retention_deletes_and_expires_what_is_due(db):
    _shop(db)
    _receive(db, _relay(eventId="old"))
    _receive(db, _relay(eventId="recent"))
    _age(db, ServerEvent, 31, event_id="old")
    _browser_purchase(db)
    _age(db, PendingPurchase, 8)

    result = run_daily_retention(db)

    assert result == {"server_events_deleted": 1, "pending_purchases_expired": 1, "paused_expired": 0}
    assert [e.event_id for e in db.scalars(select(ServerEvent).order_by(ServerEvent.created_at))] == [
        "recent", "purchase-5551234"
    ]


@pytest.mark.integration
def test_paused_events_past_seven_days_fail(db):
    _shop(db)
    _receive(db)
    _sender(db, FakeMetaApi(MetaAnswer(status=400, body={"error": {"code": 190, "message": "x"}}))).send_due()
    _age(db, ServerEvent, 8)

    assert run_daily_retention(db)["paused_expired"] == 1
    assert db.scalar(select(ServerEvent)).status == ServerEventStatus.FAILED
