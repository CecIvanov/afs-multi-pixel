"""Markets and the Pixel Mapping (spec §2, §4, §6): syncing the shop's Markets,
and saving, checking and removing a Market's pixel ID + Conversions API token pair.
Shopify and Meta are replaced by fakes at the MarketService seam."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Market, MarketPixel, TokenState
from app.services.market_service import (
    MarketService,
    PixelCheck,
    PixelValidationError,
    ShopMarket,
    interpret_pixel_check,
    parse_market_node,
)
from app.services.tenant_service import TenantService
from app.services.token_cipher import TokenCipher, load_token_key

SHOP = "markets-shop.myshopify.com"
KEY_HEX = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
PIXEL = "1290457710338842"
TOKEN = "EAAJZBexampleConversionsApiToken0123456789"

BG = ShopMarket(shopify_market_id=101, name="Bulgaria", market_type="REGION", status="ACTIVE", regions=["Bulgaria"])
GR = ShopMarket(shopify_market_id=102, name="Greece", market_type="REGION", status="ACTIVE", regions=["Greece", "Cyprus"])
HU = ShopMarket(shopify_market_id=103, name="Hungary", market_type="REGION", status="ACTIVE", regions=["Hungary"])


class FakeShopify:
    def __init__(self, markets: list[ShopMarket]) -> None:
        self.markets = markets

    def __call__(self, tenant) -> list[ShopMarket]:
        return list(self.markets)


class FakeMeta:
    """Answers Check with Meta; records the token each check was made with."""

    def __init__(self, result: PixelCheck | None = None) -> None:
        self.result = result or PixelCheck(ok=True, pixel_name="Dontmiss BG", owner_name="Dontmiss Ltd")
        self.calls: list[tuple[str, str]] = []

    def __call__(self, pixel_id: str, token: str) -> PixelCheck:
        self.calls.append((pixel_id, token))
        return self.result


def _tenant(db):
    return TenantService(db).sync_shopify_install(SHOP, access_token="shpat_x", scopes="read_markets")


def _service(db, markets=(BG, GR), meta: FakeMeta | None = None) -> MarketService:
    return MarketService(
        db,
        fetch_markets=FakeShopify(list(markets)),
        check_pixel=meta or FakeMeta(),
        cipher=TokenCipher(load_token_key(KEY_HEX)),
    )


# --- parsing the Admin API -------------------------------------------------------
@pytest.mark.unit
def test_parse_market_node_normalises_the_gid_to_the_numeric_id():
    node = {
        "id": "gid://shopify/Market/6157828161",
        "name": "Greece",
        "type": "REGION",
        "status": "ACTIVE",
        "conditions": {"regionsCondition": {"regions": {"nodes": [{"name": "Greece"}, {"name": "Cyprus"}]}}},
    }

    market = parse_market_node(node)

    assert market == ShopMarket(
        shopify_market_id=6157828161, name="Greece", market_type="REGION", status="ACTIVE", regions=["Greece", "Cyprus"]
    )


@pytest.mark.unit
def test_parse_market_node_without_region_conditions_has_no_regions():
    node = {"id": "gid://shopify/Market/9", "name": "Wholesale BG", "type": "COMPANY_LOCATION", "status": "DRAFT",
            "conditions": {"regionsCondition": None}}

    assert parse_market_node(node).regions == []


# --- interpreting Check with Meta --------------------------------------------------
@pytest.mark.unit
def test_pixel_check_passes_when_meta_returns_the_pixel():
    body = {"id": PIXEL, "name": "Dontmiss BG", "owner_business": {"id": "77", "name": "Dontmiss Ltd"},
            "is_unavailable": False}

    assert interpret_pixel_check(PIXEL, 200, body) == PixelCheck(
        ok=True, pixel_name="Dontmiss BG", owner_name="Dontmiss Ltd"
    )


@pytest.mark.unit
def test_pixel_check_fails_with_metas_error_message():
    body = {"error": {"message": "Error validating access token: Session has expired", "code": 190}}

    check = interpret_pixel_check(PIXEL, 400, body)

    assert check.ok is False
    assert "Session has expired" in (check.error or "")


@pytest.mark.unit
def test_pixel_check_fails_for_an_unavailable_pixel():
    body = {"id": PIXEL, "name": "Old pixel", "is_unavailable": True}

    assert interpret_pixel_check(PIXEL, 200, body).ok is False


@pytest.mark.unit
def test_pixel_check_fails_when_meta_answers_for_another_id():
    assert interpret_pixel_check(PIXEL, 200, {"id": "999", "name": "x"}).ok is False


# --- syncing Markets ---------------------------------------------------------------
@pytest.mark.integration
def test_first_sync_stores_the_shops_markets_none_of_them_new(db):
    tenant = _tenant(db)

    views = _service(db).sync(tenant)

    assert [(v.shopify_market_id, v.name, v.regions) for v in views] == [
        (101, "Bulgaria", ["Bulgaria"]),
        (102, "Greece", ["Greece", "Cyprus"]),
    ]
    assert not any(v.is_new for v in views)
    assert all(v.pixel is None for v in views)


@pytest.mark.integration
def test_a_market_added_later_shows_as_new_and_unmapped(db):
    tenant = _tenant(db)
    _service(db, markets=(BG, GR)).sync(tenant)

    views = _service(db, markets=(BG, GR, HU)).sync(tenant)

    hungary = next(v for v in views if v.shopify_market_id == 103)
    assert hungary.is_new and hungary.pixel is None
    assert not any(v.is_new for v in views if v.shopify_market_id != 103)


@pytest.mark.integration
def test_a_new_market_stops_being_new_after_seven_days(db):
    tenant = _tenant(db)
    _service(db, markets=(BG,)).sync(tenant)
    _service(db, markets=(BG, HU)).sync(tenant)
    row = db.scalar(select(Market).where(Market.shopify_market_id == 103))
    row.first_seen_at = datetime.now(UTC) - timedelta(days=8)
    db.commit()

    views = _service(db, markets=(BG, HU)).list_markets(tenant)

    assert not any(v.is_new for v in views)


@pytest.mark.integration
def test_sync_updates_a_renamed_or_drafted_market(db):
    tenant = _tenant(db)
    _service(db, markets=(BG,)).sync(tenant)
    renamed = ShopMarket(shopify_market_id=101, name="България", market_type="REGION", status="DRAFT", regions=["Bulgaria"])

    views = _service(db, markets=(renamed,)).sync(tenant)

    assert [(v.name, v.status) for v in views] == [("България", "DRAFT")]


@pytest.mark.integration
def test_a_deleted_market_disappears_with_its_mapping(db):
    tenant = _tenant(db)
    service = _service(db, markets=(BG, GR))
    service.sync(tenant)
    service.save_pixel(tenant, 102, pixel_id=PIXEL, token=TOKEN)

    views = _service(db, markets=(BG,)).sync(tenant)

    assert [v.shopify_market_id for v in views] == [101]
    assert db.scalars(select(MarketPixel).where(MarketPixel.tenant_id == tenant.id)).all() == []


@pytest.mark.integration
def test_markets_are_kept_per_shop(db):
    tenant = _tenant(db)
    other = TenantService(db).sync_shopify_install("other-shop.myshopify.com", access_token="shpat_y")
    _service(db, markets=(BG,)).sync(other)

    views = _service(db, markets=(GR,)).sync(tenant)

    assert [v.shopify_market_id for v in views] == [102]
    assert [v.shopify_market_id for v in _service(db).list_markets(other)] == [101]


# --- the pixel ID + token pair -------------------------------------------------------
@pytest.mark.integration
def test_saving_stores_the_pixel_and_the_token_encrypted(db):
    tenant = _tenant(db)
    service = _service(db)
    service.sync(tenant)

    view = service.save_pixel(tenant, 101, pixel_id=PIXEL, token=TOKEN, test_event_code="TEST123")

    row = db.scalar(select(MarketPixel).where(MarketPixel.shopify_market_id == 101))
    assert row.capi_token_encrypted and TOKEN not in row.capi_token_encrypted
    assert TokenCipher(load_token_key(KEY_HEX)).decrypt(row.capi_token_encrypted) == TOKEN
    assert (row.pixel_id, row.pixel_name, row.test_event_code, row.token_state) == (
        PIXEL, "Dontmiss BG", "TEST123", TokenState.OK
    )
    assert view.pixel is not None and view.pixel.pixel_id == PIXEL and view.pixel.has_token


@pytest.mark.integration
@pytest.mark.parametrize("pixel_id", ["", "123456789012345678901", "12345678901234a"])
def test_saving_refuses_a_pixel_id_that_isnt_up_to_20_digits(db, pixel_id):
    tenant = _tenant(db)
    service = _service(db)
    service.sync(tenant)

    with pytest.raises(PixelValidationError):
        service.save_pixel(tenant, 101, pixel_id=pixel_id, token=TOKEN)


@pytest.mark.integration
def test_saving_refuses_a_new_pixel_without_a_token(db):
    tenant = _tenant(db)
    service = _service(db)
    service.sync(tenant)

    with pytest.raises(PixelValidationError):
        service.save_pixel(tenant, 101, pixel_id=PIXEL, token="  ")
    assert db.scalars(select(MarketPixel)).all() == []


@pytest.mark.integration
def test_saving_refuses_a_pair_that_fails_check_with_meta(db):
    tenant = _tenant(db)
    meta = FakeMeta(PixelCheck(ok=False, error="Meta refused the check: Invalid OAuth access token"))
    service = _service(db, meta=meta)
    service.sync(tenant)

    with pytest.raises(PixelValidationError, match="Invalid OAuth"):
        service.save_pixel(tenant, 101, pixel_id=PIXEL, token=TOKEN)
    assert db.scalars(select(MarketPixel)).all() == []


@pytest.mark.integration
def test_saving_refuses_a_market_the_shop_doesnt_have(db):
    tenant = _tenant(db)
    service = _service(db)
    service.sync(tenant)

    with pytest.raises(LookupError):
        service.save_pixel(tenant, 999, pixel_id=PIXEL, token=TOKEN)


@pytest.mark.integration
def test_editing_without_a_new_token_keeps_and_rechecks_the_stored_one(db):
    tenant = _tenant(db)
    meta = FakeMeta()
    service = _service(db, meta=meta)
    service.sync(tenant)
    service.save_pixel(tenant, 101, pixel_id=PIXEL, token=TOKEN)

    service.save_pixel(tenant, 101, pixel_id="5521938804417730", token=None, test_event_code="")

    row = db.scalar(select(MarketPixel).where(MarketPixel.shopify_market_id == 101))
    assert row.pixel_id == "5521938804417730" and row.test_event_code is None
    assert TokenCipher(load_token_key(KEY_HEX)).decrypt(row.capi_token_encrypted) == TOKEN
    assert meta.calls[-1] == ("5521938804417730", TOKEN)


@pytest.mark.integration
def test_a_rejected_token_must_be_replaced_and_the_new_one_clears_the_problem(db):
    tenant = _tenant(db)
    service = _service(db)
    service.sync(tenant)
    service.save_pixel(tenant, 101, pixel_id=PIXEL, token=TOKEN)
    row = db.scalar(select(MarketPixel).where(MarketPixel.shopify_market_id == 101))
    row.token_state = TokenState.REJECTED
    db.commit()

    with pytest.raises(PixelValidationError):
        service.save_pixel(tenant, 101, pixel_id=PIXEL, token=None)
    view = service.save_pixel(tenant, 101, pixel_id=PIXEL, token=TOKEN + "new")

    assert view.pixel is not None and view.pixel.token_state == "ok"


@pytest.mark.integration
def test_a_mapped_market_is_no_longer_new(db):
    tenant = _tenant(db)
    _service(db, markets=(BG,)).sync(tenant)
    _service(db, markets=(BG, HU)).sync(tenant)

    view = _service(db, markets=(BG, HU)).save_pixel(tenant, 103, pixel_id=PIXEL, token=TOKEN)

    assert view.is_new is False


@pytest.mark.integration
def test_check_uses_the_stored_token_when_none_is_given(db):
    tenant = _tenant(db)
    meta = FakeMeta()
    service = _service(db, meta=meta)
    service.sync(tenant)
    service.save_pixel(tenant, 101, pixel_id=PIXEL, token=TOKEN)

    check = service.check_pixel(tenant, 101, pixel_id=PIXEL, token=None)

    assert check.ok and check.owner_name == "Dontmiss Ltd"
    assert meta.calls[-1] == (PIXEL, TOKEN)


@pytest.mark.integration
def test_check_without_any_token_fails_without_calling_meta(db):
    tenant = _tenant(db)
    meta = FakeMeta()
    service = _service(db, meta=meta)
    service.sync(tenant)

    with pytest.raises(PixelValidationError):
        service.check_pixel(tenant, 101, pixel_id=PIXEL, token=None)
    assert meta.calls == []


@pytest.mark.integration
def test_removing_the_pixel_unmaps_the_market(db):
    tenant = _tenant(db)
    service = _service(db)
    service.sync(tenant)
    service.save_pixel(tenant, 101, pixel_id=PIXEL, token=TOKEN)

    view = service.remove_pixel(tenant, 101)

    assert view.pixel is None
    assert db.scalars(select(MarketPixel)).all() == []


@pytest.mark.integration
def test_an_empty_answer_from_shopify_never_wipes_the_mapping(db):
    # Every shop has at least its primary Market; an empty list is a bad answer.
    tenant = _tenant(db)
    service = _service(db, markets=(BG,))
    service.sync(tenant)
    service.save_pixel(tenant, 101, pixel_id=PIXEL, token=TOKEN)

    with pytest.raises(RuntimeError):
        _service(db, markets=()).sync(tenant)

    assert [v.shopify_market_id for v in _service(db).list_markets(tenant)] == [101]
    assert len(db.scalars(select(MarketPixel)).all()) == 1


# --- the real Shopify and Meta clients -----------------------------------------------
@pytest.mark.unit
def test_fetch_shop_markets_follows_pagination(monkeypatch):
    from app.services import shopify_markets_client

    pages = {
        None: {"nodes": [{"id": "gid://shopify/Market/1", "name": "A", "type": "REGION", "status": "ACTIVE"}],
               "pageInfo": {"hasNextPage": True, "endCursor": "c1"}},
        "c1": {"nodes": [{"id": "gid://shopify/Market/2", "name": "B", "type": "REGION", "status": "DRAFT"}],
               "pageInfo": {"hasNextPage": False, "endCursor": "c2"}},
    }
    seen_cursors = []

    def fake_graphql(*, shop_domain, access_token, query, variables=None):
        seen_cursors.append(variables["after"])
        return {"data": {"markets": pages[variables["after"]]}}

    monkeypatch.setattr(shopify_markets_client, "admin_graphql", fake_graphql)

    class T:
        shop_domain = SHOP
        access_token = "shpat_x"

    markets = shopify_markets_client.fetch_shop_markets(T())

    assert [(m.shopify_market_id, m.status) for m in markets] == [(1, "ACTIVE"), (2, "DRAFT")]
    assert seen_cursors == [None, "c1"]


@pytest.mark.unit
def test_check_pixel_with_meta_sends_the_documented_request(monkeypatch):
    import httpx

    from app.services import meta_pixel_client

    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": PIXEL, "name": "Dontmiss BG", "owner_business": {"name": "Dontmiss Ltd"}})

    monkeypatch.setattr(meta_pixel_client, "_transport", httpx.MockTransport(handler))

    check = meta_pixel_client.check_pixel_with_meta(PIXEL, TOKEN)

    assert check == PixelCheck(ok=True, pixel_name="Dontmiss BG", owner_name="Dontmiss Ltd")
    (request,) = requests
    assert request.method == "GET"
    assert request.url.path.endswith(f"/{PIXEL}")
    assert request.url.params["fields"] == "id,name,owner_business,is_unavailable"
    assert request.url.params["access_token"] == TOKEN


# --- when Markets are synced ------------------------------------------------------------
def _drain(db) -> None:
    from app.services.async_job_service import AsyncJobService

    svc = AsyncJobService(db)
    while (job := svc.claim_next("worker-1")) is not None:
        svc.process_job(job.id)


@pytest.fixture()
def shopify_has(monkeypatch):
    """Point the real Market fetch at a fake shop and keep the install-time
    shop-info fetch away from Shopify."""
    from app.services import job_processors, shopify_markets_client
    from app.models import AsyncJobOperation

    fake = FakeShopify([BG, GR])
    monkeypatch.setattr(shopify_markets_client, "fetch_shop_markets", fake)
    monkeypatch.setitem(job_processors._REGISTRY, AsyncJobOperation.SHOP_INFO_FETCH, lambda db, job: None)
    return fake


@pytest.mark.integration
def test_install_syncs_the_markets_in_the_worker(db, shopify_has):
    tenant = _tenant(db)

    _drain(db)

    assert [v.shopify_market_id for v in _service(db).list_markets(tenant)] == [101, 102]


@pytest.mark.integration
def test_markets_webhooks_resync_through_the_inbox(db, shopify_has):
    from app.services.webhook_ingest_service import WebhookIngestService

    tenant = _tenant(db)
    _drain(db)
    shopify_has.markets = [BG, HU]

    WebhookIngestService(db).ingest(shop_domain=SHOP, topic="markets/create", shopify_webhook_id="m1", payload={"id": 103})
    WebhookIngestService(db).ingest(shop_domain=SHOP, topic="markets/delete", shopify_webhook_id="m2", payload={"id": 102})
    _drain(db)

    views = _service(db).list_markets(tenant)
    assert [(v.shopify_market_id, v.is_new) for v in views] == [(101, False), (103, True)]


@pytest.mark.integration
def test_shop_redact_deletes_the_shops_markets(db):
    from app.services.compliance_service import ComplianceService

    tenant = _tenant(db)
    _service(db).sync(tenant)

    ComplianceService(db).redact_shop_data(SHOP)

    assert db.scalars(select(Market)).all() == []
