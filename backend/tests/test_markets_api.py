"""The internal Markets API the BFF calls for the Market health page (spec §4).
MarketService's Shopify and Meta seams are faked through the get_market_service
dependency."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import MarketPixel
from app.services.market_service import MarketService, PixelCheck
from app.services.token_cipher import TokenCipher, load_token_key
from tests.conftest import INTERNAL_HEADERS
from tests.test_markets import BG, GR, KEY_HEX, PIXEL, SHOP, TOKEN, FakeMeta, FakeShopify, _tenant

BASE = f"/api/v1/internal/tenants/by-shop/{SHOP}/markets"


@pytest.fixture()
def fakes(db):
    from app.api.internal_routes import get_market_service
    from app.main import app

    shopify, meta = FakeShopify([BG, GR]), FakeMeta()
    cipher = TokenCipher(load_token_key(KEY_HEX))

    def override():
        return MarketService(db, fetch_markets=shopify, check_pixel=meta, cipher=cipher)

    app.dependency_overrides[get_market_service] = override
    yield shopify, meta
    app.dependency_overrides.pop(get_market_service, None)


@pytest.mark.integration
def test_listing_with_sync_returns_the_fetched_markets(db, client, fakes):
    _tenant(db)

    response = client.get(BASE, params={"sync": "true"}, headers=INTERNAL_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["sync_error"] is None
    assert [(m["shopify_market_id"], m["name"], m["pixel"]) for m in body["markets"]] == [
        (101, "Bulgaria", None),
        (102, "Greece", None),
    ]


@pytest.mark.integration
def test_a_failed_sync_still_lists_the_stored_markets(db, client, fakes):
    shopify, _ = fakes
    _tenant(db)
    client.get(BASE, params={"sync": "true"}, headers=INTERNAL_HEADERS)
    shopify.markets = []  # Shopify answers badly

    body = client.get(BASE, params={"sync": "true"}, headers=INTERNAL_HEADERS).json()

    assert body["sync_error"]
    assert [m["shopify_market_id"] for m in body["markets"]] == [101, 102]


@pytest.mark.integration
def test_unknown_shop_is_404(client, fakes):
    assert client.get(BASE, headers=INTERNAL_HEADERS).status_code == 404


@pytest.mark.integration
def test_check_returns_metas_answer(db, client, fakes):
    _tenant(db)
    client.get(BASE, params={"sync": "true"}, headers=INTERNAL_HEADERS)

    response = client.post(f"{BASE}/101/pixel/check", json={"pixel_id": PIXEL, "token": TOKEN}, headers=INTERNAL_HEADERS)

    assert response.status_code == 200
    assert response.json() == {"ok": True, "pixel_name": "Dontmiss BG", "error": None}


@pytest.mark.integration
def test_save_maps_the_market_and_never_returns_the_token(db, client, fakes):
    _tenant(db)
    client.get(BASE, params={"sync": "true"}, headers=INTERNAL_HEADERS)

    response = client.put(
        f"{BASE}/101/pixel", json={"pixel_id": PIXEL, "token": TOKEN, "test_event_code": "TEST1"}, headers=INTERNAL_HEADERS
    )

    assert response.status_code == 200
    assert TOKEN not in response.text
    pixel = response.json()["pixel"]
    assert {k: pixel[k] for k in ("pixel_id", "pixel_name", "test_event_code", "token_state", "has_token", "active")} == {
        "pixel_id": PIXEL, "pixel_name": "Dontmiss BG", "test_event_code": "TEST1", "token_state": "ok", "has_token": True,
        "active": True,
    }
    assert (pixel["token_hint"], pixel["last_check_ok"]) == (TOKEN[-4:], True)


@pytest.mark.integration
def test_save_without_a_token_is_422_with_the_reason(db, client, fakes):
    _tenant(db)
    client.get(BASE, params={"sync": "true"}, headers=INTERNAL_HEADERS)

    response = client.put(f"{BASE}/101/pixel", json={"pixel_id": PIXEL, "token": ""}, headers=INTERNAL_HEADERS)

    assert response.status_code == 422
    assert "token" in response.json()["detail"]
    assert db.scalars(select(MarketPixel)).all() == []


@pytest.mark.integration
def test_save_that_fails_check_with_meta_is_422(db, client, fakes):
    _, meta = fakes
    meta.result = PixelCheck(ok=False, error="Meta refused the check: Invalid OAuth access token")
    _tenant(db)
    client.get(BASE, params={"sync": "true"}, headers=INTERNAL_HEADERS)

    response = client.put(f"{BASE}/101/pixel", json={"pixel_id": PIXEL, "token": TOKEN}, headers=INTERNAL_HEADERS)

    assert response.status_code == 422
    assert "Invalid OAuth" in response.json()["detail"]


@pytest.mark.integration
def test_save_for_a_market_the_shop_doesnt_have_is_404(db, client, fakes):
    _tenant(db)
    client.get(BASE, params={"sync": "true"}, headers=INTERNAL_HEADERS)

    response = client.put(f"{BASE}/999/pixel", json={"pixel_id": PIXEL, "token": TOKEN}, headers=INTERNAL_HEADERS)

    assert response.status_code == 404


@pytest.mark.integration
def test_remove_unmaps_the_market(db, client, fakes):
    _tenant(db)
    client.get(BASE, params={"sync": "true"}, headers=INTERNAL_HEADERS)
    client.put(f"{BASE}/101/pixel", json={"pixel_id": PIXEL, "token": TOKEN}, headers=INTERNAL_HEADERS)

    response = client.delete(f"{BASE}/101/pixel", headers=INTERNAL_HEADERS)

    assert response.status_code == 200
    assert response.json()["pixel"] is None


# --- Relay intake, stats, event log and setup (spec §3.2, §4) ---------------------------
@pytest.mark.integration
def test_relay_endpoint_stores_a_valid_relay(db, client, fakes, monkeypatch):
    from app.config import get_settings
    from app.services import relay_service
    from app.services.relay_crypto import relay_key_pair

    monkeypatch.setattr(get_settings(), "token_enc_key", KEY_HEX)
    monkeypatch.setattr(relay_service, "_LIMITER", relay_service.InMemoryRateLimiter())
    from tests.test_publishing import CIPHER, browser_envelope
    from tests.test_relay import _relay, _shop

    _shop(db)
    body = browser_envelope(relay_key_pair(db, CIPHER).public_key, _relay())

    response = client.post(
        "/api/v1/internal/relay",
        json={"body": body, "origin": "https://dontmiss.bg", "ip": "203.0.113.7", "user_agent": "UA"},
        headers=INTERNAL_HEADERS,
    )

    assert response.status_code == 200 and response.json() == {"outcome": "stored"}


@pytest.mark.integration
def test_markets_listing_carries_counts_summary_and_setup(db, client, fakes):
    from tests.test_relay import _receive, _shop

    _shop(db)
    _receive(db)

    body = client.get(BASE, headers=INTERNAL_HEADERS).json()

    bg = next(m for m in body["markets"] if m["shopify_market_id"] == 101)
    assert bg["stats"]["browser"] == 1 and len(bg["stats"]["series"]) == 24
    assert body["summary"] == {"browser_24h": 1, "server_24h": 0}
    assert body["setup"] == {"consent_confirmed": False, "verified_in_meta": False}


@pytest.mark.integration
def test_the_merchant_confirms_setup_steps(db, client, fakes):
    _tenant(db)

    response = client.post(f"/api/v1/internal/tenants/by-shop/{SHOP}/setup", json={"verified_in_meta": True},
                           headers=INTERNAL_HEADERS)

    assert response.json() == {"consent_confirmed": False, "verified_in_meta": True}


# --- the Market page (#15) -------------------------------------------------------------------
@pytest.mark.integration
def test_the_market_page_carries_the_market_and_its_figures_for_the_range(db, client, fakes):
    from tests.test_relay import _receive, _relay, _shop

    _shop(db)
    _receive(db, _relay(eventId="a"))

    body = client.get(f"{BASE}/101", params={"range": "7d"}, headers=INTERNAL_HEADERS).json()

    assert body["market"]["name"] == "Bulgaria"
    assert body["market"]["pixel"]["active"] is True
    assert body["detail"]["range"] == "7d"
    assert body["detail"]["browser"] == 1 and len(body["detail"]["series"]) == 7
    assert body["detail"]["types"] == [{"event_name": "ViewContent", "count": 1, "sent": 0}]


@pytest.mark.integration
def test_the_market_page_refuses_an_unknown_range_or_market(db, client, fakes):
    _tenant(db)
    client.get(BASE, params={"sync": "true"}, headers=INTERNAL_HEADERS)

    assert client.get(f"{BASE}/101", params={"range": "1y"}, headers=INTERNAL_HEADERS).status_code == 422
    assert client.get(f"{BASE}/999", headers=INTERNAL_HEADERS).status_code == 404


@pytest.mark.integration
def test_the_event_table_endpoint_filters_searches_and_pages(db, client, fakes):
    from tests.test_relay import _receive, _relay, _shop

    _shop(db)
    _receive(db, _relay(eventId="purchase-42"))
    _receive(db, _relay(eventId="b"))
    _receive(db, _relay(eventId="c", marketId="102"))

    body = client.get(
        f"{BASE}/101/events", params={"range": "24h", "status": "waiting", "q": "42", "page": 1},
        headers=INTERNAL_HEADERS,
    ).json()

    assert [(r["event_id"], r["sent_as"], r["status"]) for r in body["rows"]] == [("purchase-42", "Server", "waiting")]
    assert (body["total"], body["page"], body["page_size"]) == (1, 1, 50)
    assert body["event_counts"] == {"ViewContent": 1}
    assert body["status_counts"] == {"waiting": 1}


@pytest.mark.integration
def test_deactivate_reactivate_and_recheck(db, client, fakes):
    _, meta = fakes
    _tenant(db)
    client.get(BASE, params={"sync": "true"}, headers=INTERNAL_HEADERS)
    client.put(f"{BASE}/101/pixel", json={"pixel_id": PIXEL, "token": TOKEN}, headers=INTERNAL_HEADERS)

    off = client.post(f"{BASE}/101/pixel/deactivate", headers=INTERNAL_HEADERS).json()
    on = client.post(f"{BASE}/101/pixel/reactivate", headers=INTERNAL_HEADERS).json()
    meta.result = PixelCheck(ok=False, error="Meta refused the check: expired")
    check = client.post(f"{BASE}/101/pixel/recheck", headers=INTERNAL_HEADERS).json()

    assert (off["pixel"]["active"], on["pixel"]["active"]) == (False, True)
    assert check == {"ok": False, "pixel_name": None, "error": "Meta refused the check: expired"}
    assert client.post(f"{BASE}/102/pixel/deactivate", headers=INTERNAL_HEADERS).status_code == 404
