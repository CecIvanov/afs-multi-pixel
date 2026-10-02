"""Publish what the storefront needs (spec §5, §8): the Pixel Mapping, the Relay
public key and endpoint, mirrored to the app-owned metafield
``multi_pixel.mapping`` (read by the theme app embed) and to the Web Pixel's
settings. Also keeps the shop's storefront host allowlist for the Relay's Origin
check. Conversions API tokens never leave the backend.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.logging_config import get_logger
from app.models import AsyncJobOperation, MarketPixel, Tenant, TenantStatus
from app.services.relay_crypto import relay_key_pair
from app.services.token_cipher import TokenCipher

logger = get_logger().child({"component": "storefront_publisher"})

METAFIELD_NAMESPACE = "multi_pixel"
METAFIELD_KEY = "mapping"

Graphql = Callable[[Tenant, str, "dict[str, Any] | None"], dict[str, Any]]

INSTALLATION_QUERY = "query MultiPixelInstallation { currentAppInstallation { id } }"
SET_METAFIELD = """
mutation MultiPixelSetMapping($metafields: [MetafieldsSetInput!]!) {
  metafieldsSet(metafields: $metafields) { userErrors { field message } }
}
"""
WEB_PIXEL_QUERY = "query MultiPixelWebPixel { webPixel { id } }"
CREATE_WEB_PIXEL = """
mutation MultiPixelCreateWebPixel($webPixel: WebPixelInput!) {
  webPixelCreate(webPixel: $webPixel) { userErrors { field message } webPixel { id } }
}
"""
UPDATE_WEB_PIXEL = """
mutation MultiPixelUpdateWebPixel($id: ID!, $webPixel: WebPixelInput!) {
  webPixelUpdate(id: $id, webPixel: $webPixel) { userErrors { field message } }
}
"""
HOSTS_QUERY = """
query StorefrontHosts($after: String) {
  shop { myshopifyDomain primaryDomain { host } }
  markets(first: 100, after: $after) {
    nodes { webPresences(first: 50) { nodes { domain { host } } } }
    pageInfo { hasNextPage endCursor }
  }
}
"""


def _admin_graphql(tenant: Tenant, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    from app.services.shopify_shop_info_service import admin_graphql

    payload = admin_graphql(
        shop_domain=tenant.shop_domain, access_token=tenant.access_token or "", query=query, variables=variables
    )
    return payload.get("data") or {}


def relay_endpoint(app_url: str) -> str:
    return f"{app_url.rstrip('/')}/api/events"


class StorefrontPublisher:
    def __init__(
        self,
        db: Session,
        *,
        graphql: Graphql | None = None,
        cipher: TokenCipher | None = None,
        app_url: str | None = None,
    ) -> None:
        self.db = db
        self._graphql = graphql or _admin_graphql
        self._cipher = cipher
        self._app_url = app_url if app_url is not None else get_settings().shopify_app_url

    def publish(self, tenant: Tenant) -> None:
        if not self._app_url:
            raise RuntimeError("SHOPIFY_APP_URL isn't set; the storefront wouldn't know where to send Relays")
        pixels = {
            str(p.shopify_market_id): p.pixel_id
            for p in self.db.scalars(
                # A deactivated pixel sends nothing, so the storefront doesn't learn of it.
                select(MarketPixel).where(MarketPixel.tenant_id == tenant.id, MarketPixel.active.is_(True))
            )
        }
        public_key = relay_key_pair(self.db, self._cipher_or_default()).public_key
        endpoint = relay_endpoint(self._app_url)

        installation = self._graphql(tenant, INSTALLATION_QUERY, None)["currentAppInstallation"]["id"]
        metafield = self._graphql(
            tenant,
            SET_METAFIELD,
            {
                "metafields": [
                    {
                        "ownerId": installation,
                        "namespace": METAFIELD_NAMESPACE,
                        "key": METAFIELD_KEY,
                        "type": "json",
                        "value": json.dumps({"pixels": pixels, "publicKey": public_key, "endpoint": endpoint}),
                    }
                ]
            },
        )
        _raise_on_user_errors("metafieldsSet", metafield.get("metafieldsSet"))

        # The Web Pixel's settings are flat strings (see its shopify.extension.toml).
        settings = json.dumps({"mapping": json.dumps(pixels), "publicKey": public_key, "endpoint": endpoint})
        web_pixel_id = self._web_pixel_id(tenant)
        if web_pixel_id:
            result = self._graphql(tenant, UPDATE_WEB_PIXEL, {"id": web_pixel_id, "webPixel": {"settings": settings}})
            _raise_on_user_errors("webPixelUpdate", result.get("webPixelUpdate"))
        else:
            result = self._graphql(tenant, CREATE_WEB_PIXEL, {"webPixel": {"settings": settings}})
            _raise_on_user_errors("webPixelCreate", result.get("webPixelCreate"))
        logger.info("storefront.published", {"tenantId": str(tenant.id), "pixels": len(pixels)})

    def sync_storefront_hosts(self, tenant: Tenant) -> list[str]:
        hosts: set[str] = {tenant.shop_domain}
        after: str | None = None
        while True:
            data = self._graphql(tenant, HOSTS_QUERY, {"after": after})
            shop = data.get("shop") or {}
            hosts.add(shop.get("myshopifyDomain") or tenant.shop_domain)
            if (shop.get("primaryDomain") or {}).get("host"):
                hosts.add(shop["primaryDomain"]["host"])
            markets = data.get("markets") or {}
            for market in markets.get("nodes") or []:
                for presence in (market.get("webPresences") or {}).get("nodes") or []:
                    if (presence.get("domain") or {}).get("host"):
                        hosts.add(presence["domain"]["host"])
            page = markets.get("pageInfo") or {}
            if not page.get("hasNextPage"):
                break
            after = page.get("endCursor")
        tenant.storefront_hosts = sorted(h.lower() for h in hosts)
        tenant.storefront_hosts_synced_at = datetime.now(UTC)
        self.db.commit()
        logger.info("storefront.hosts_synced", {"tenantId": str(tenant.id), "hosts": len(tenant.storefront_hosts)})
        return tenant.storefront_hosts

    def _web_pixel_id(self, tenant: Tenant) -> str | None:
        # The webPixel query errors (rather than returning null) while the app has
        # none. Any other error (auth, throttling, network) must surface as itself.
        try:
            return (self._graphql(tenant, WEB_PIXEL_QUERY, None).get("webPixel") or {}).get("id")
        except Exception as exc:  # noqa: BLE001
            if "pixel" in str(exc).lower():
                return None
            raise

    def _cipher_or_default(self) -> TokenCipher:
        if self._cipher is None:
            from app.services.token_cipher import token_cipher_from_settings

            self._cipher = token_cipher_from_settings()
        return self._cipher


def _raise_on_user_errors(operation: str, result: dict[str, Any] | None) -> None:
    errors = (result or {}).get("userErrors") or []
    if errors:
        raise RuntimeError(f"{operation}: {'; '.join(str(e.get('message')) for e in errors)}")


def queue_publish(db: Session, tenant_id) -> None:
    from app.services.async_job_service import AsyncJobService

    AsyncJobService(db).enqueue(
        tenant_id=tenant_id, operation=AsyncJobOperation.PIXEL_MAPPING_PUBLISH, topic="pixel_mapping/publish"
    )


def queue_publish_for_all_shops(db: Session) -> int:
    """App start: republish the key and endpoint to every installed shop (spec §8),
    so a redeploy or a new app URL needs no merchant action."""
    tenants = db.scalars(select(Tenant).where(Tenant.status == TenantStatus.ACTIVE)).all()
    for tenant in tenants:
        queue_publish(db, tenant.id)
    return len(tenants)
