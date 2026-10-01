"""Publishing the Pixel Mapping (spec §5, §8): the Relay key pair, the app-owned
metafield and the Web Pixel's settings, and the storefront host allowlist. The
Admin API is replaced by a fake at the StorefrontPublisher seam."""

from __future__ import annotations

import base64
import json
import os

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select

from app.models import AppKey, AsyncJob, AsyncJobOperation, MarketPixel
from app.services.relay_crypto import RelayDecryptError, decrypt_envelope, relay_key_pair
from app.services.storefront_publisher import StorefrontPublisher
from app.services.token_cipher import TokenCipher, load_token_key
from tests.test_markets import BG, GR, KEY_HEX, PIXEL, TOKEN, _service, _tenant

CIPHER = TokenCipher(load_token_key(KEY_HEX))


def browser_envelope(public_key_b64: str, payload: dict) -> str:
    """What the theme embed and Web Pixel send: AES-GCM data, RSA-OAEP(SHA-256) key."""
    public_key = serialization.load_der_public_key(base64.b64decode(public_key_b64))
    aes_key, iv = AESGCM.generate_key(bit_length=256), os.urandom(12)
    data = AESGCM(aes_key).encrypt(iv, json.dumps(payload).encode(), None)
    key = public_key.encrypt(
        aes_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return json.dumps({"v": 1, "k": b64(key), "iv": b64(iv), "d": b64(data)})


class FakeAdmin:
    """Records every Admin GraphQL call and answers the few the publisher makes."""

    def __init__(self, *, web_pixel_id: str | None = None, hosts: dict | None = None) -> None:
        self.web_pixel_id = web_pixel_id
        self.hosts = hosts or {}
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, tenant, query: str, variables: dict | None = None) -> dict:
        self.calls.append((query, variables or {}))
        if "currentAppInstallation" in query:
            return {"currentAppInstallation": {"id": "gid://shopify/AppInstallation/1"}}
        if "MultiPixelWebPixel" in query:
            if self.web_pixel_id is None:
                raise RuntimeError("No web pixel was found for this app.")
            return {"webPixel": {"id": self.web_pixel_id}}
        if "metafieldsSet" in query:
            return {"metafieldsSet": {"userErrors": []}}
        if "webPixelCreate" in query:
            return {"webPixelCreate": {"userErrors": [], "webPixel": {"id": "gid://shopify/WebPixel/9"}}}
        if "webPixelUpdate" in query:
            return {"webPixelUpdate": {"userErrors": []}}
        if "StorefrontHosts" in query:
            return self.hosts
        raise AssertionError(f"unexpected query {query[:60]}")

    def variables_of(self, mutation: str) -> dict:
        return next(v for q, v in self.calls if mutation in q)


def _publisher(db, admin: FakeAdmin) -> StorefrontPublisher:
    return StorefrontPublisher(db, graphql=admin, cipher=CIPHER, app_url="https://pixel.example.com")


# --- the Relay key pair ----------------------------------------------------------------
@pytest.mark.integration
def test_the_key_pair_is_made_once_and_its_private_half_is_encrypted(db):
    first = relay_key_pair(db, CIPHER)
    second = relay_key_pair(db, CIPHER)

    assert first.public_key == second.public_key
    row = db.scalar(select(AppKey))
    assert "PRIVATE" not in row.private_key_encrypted
    assert len(db.scalars(select(AppKey)).all()) == 1


@pytest.mark.integration
def test_a_browser_envelope_decrypts_with_the_private_key(db):
    keys = relay_key_pair(db, CIPHER)
    envelope = browser_envelope(keys.public_key, {"shop": "s.myshopify.com", "event": "PageView"})

    assert decrypt_envelope(envelope, keys.private_key) == {"shop": "s.myshopify.com", "event": "PageView"}


@pytest.mark.integration
@pytest.mark.parametrize("raw", ["not json", '{"v": 2}', '{"v": 1, "k": "AA==", "iv": "AA==", "d": "AA=="}'])
def test_a_bad_envelope_is_refused(db, raw):
    keys = relay_key_pair(db, CIPHER)

    with pytest.raises(RelayDecryptError):
        decrypt_envelope(raw, keys.private_key)


# --- publishing ----------------------------------------------------------------------------
@pytest.mark.integration
def test_publish_writes_the_mapping_key_and_endpoint_to_the_metafield(db):
    tenant = _tenant(db)
    service = _service(db, markets=(BG, GR))
    service.sync(tenant)
    service.save_pixel(tenant, 101, pixel_id=PIXEL, token=TOKEN)
    admin = FakeAdmin()

    _publisher(db, admin).publish(tenant)

    (metafield,) = admin.variables_of("metafieldsSet")["metafields"]
    assert (metafield["ownerId"], metafield["namespace"], metafield["key"], metafield["type"]) == (
        "gid://shopify/AppInstallation/1", "multi_pixel", "mapping", "json"
    )
    value = json.loads(metafield["value"])
    assert value == {
        "pixels": {"101": PIXEL},
        "publicKey": relay_key_pair(db, CIPHER).public_key,
        "endpoint": "https://pixel.example.com/api/events",
    }
    assert TOKEN not in metafield["value"]


@pytest.mark.integration
def test_publish_creates_the_web_pixel_when_the_shop_has_none(db):
    tenant = _tenant(db)
    admin = FakeAdmin(web_pixel_id=None)

    _publisher(db, admin).publish(tenant)

    settings = json.loads(admin.variables_of("webPixelCreate")["webPixel"]["settings"])
    assert settings["mapping"] == "{}"
    assert settings["endpoint"] == "https://pixel.example.com/api/events"
    assert settings["publicKey"]


@pytest.mark.integration
def test_publish_updates_the_existing_web_pixel(db):
    tenant = _tenant(db)
    service = _service(db, markets=(BG,))
    service.sync(tenant)
    service.save_pixel(tenant, 101, pixel_id=PIXEL, token=TOKEN)
    admin = FakeAdmin(web_pixel_id="gid://shopify/WebPixel/5")

    _publisher(db, admin).publish(tenant)

    update = admin.variables_of("webPixelUpdate")
    assert update["id"] == "gid://shopify/WebPixel/5"
    assert json.loads(json.loads(update["webPixel"]["settings"])["mapping"]) == {"101": PIXEL}
    assert not any("webPixelCreate" in q for q, _ in admin.calls)


@pytest.mark.integration
def test_saving_or_removing_a_pixel_queues_a_publish(db):
    tenant = _tenant(db)
    service = _service(db, markets=(BG,))
    service.sync(tenant)
    db.query(AsyncJob).delete()
    db.commit()

    service.save_pixel(tenant, 101, pixel_id=PIXEL, token=TOKEN)
    service.remove_pixel(tenant, 101)

    jobs = db.scalars(select(AsyncJob).where(AsyncJob.operation == AsyncJobOperation.PIXEL_MAPPING_PUBLISH)).all()
    assert len(jobs) == 1  # coalesced while pending


@pytest.mark.integration
def test_a_sync_that_drops_a_mapped_market_queues_a_publish(db):
    tenant = _tenant(db)
    service = _service(db, markets=(BG, GR))
    service.sync(tenant)
    service.save_pixel(tenant, 102, pixel_id=PIXEL, token=TOKEN)
    db.query(AsyncJob).delete()
    db.commit()

    _service(db, markets=(BG,)).sync(tenant)

    assert db.scalar(select(AsyncJob).where(AsyncJob.operation == AsyncJobOperation.PIXEL_MAPPING_PUBLISH))
    assert db.scalars(select(MarketPixel)).all() == []


@pytest.mark.integration
def test_app_start_queues_a_publish_for_every_active_shop(db):
    from app.services.storefront_publisher import queue_publish_for_all_shops
    from app.services.tenant_service import TenantService

    _tenant(db)
    TenantService(db).sync_shopify_install("second.myshopify.com", access_token="shpat_2")
    TenantService(db).sync_shopify_uninstall("second.myshopify.com")
    db.query(AsyncJob).delete()
    db.commit()

    assert queue_publish_for_all_shops(db) == 1


# --- the storefront host allowlist ---------------------------------------------------------------
@pytest.mark.integration
def test_storefront_hosts_cover_myshopify_primary_and_market_domains(db):
    tenant = _tenant(db)
    admin = FakeAdmin(
        hosts={
            "shop": {"myshopifyDomain": "markets-shop.myshopify.com", "primaryDomain": {"host": "dontmiss.bg"}},
            "markets": {
                "nodes": [
                    {"webPresences": {"nodes": [{"domain": {"host": "dontmiss.gr"}}, {"domain": None}]}},
                    {"webPresences": {"nodes": [{"domain": {"host": "dontmiss.bg"}}]}},
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            },
        }
    )

    hosts = _publisher(db, admin).sync_storefront_hosts(tenant)

    assert hosts == ["dontmiss.bg", "dontmiss.gr", "markets-shop.myshopify.com"]
    db.refresh(tenant)
    assert tenant.storefront_hosts == hosts and tenant.storefront_hosts_synced_at is not None
