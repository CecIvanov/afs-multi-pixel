"""The shop's Markets and the Pixel Mapping (spec §2, §4, §6).

``MarketService`` is the one place that syncs Markets from Shopify and saves,
checks and removes a Market's pixel ID + Conversions API token pair. Shopify and
Meta are reached through two injected callables, so tests swap in fakes.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import Market, MarketPixel, Tenant, TokenState
from app.services.storefront_publisher import queue_publish
from app.services.token_cipher import TokenCipher

logger = get_logger().child({"component": "markets"})

PIXEL_ID = re.compile(r"^\d{15,16}$")
# An unmapped Market first seen after the shop's first sync stays "new" this long.
NEW_MARKET_WINDOW = timedelta(days=7)


class PixelValidationError(ValueError):
    """The pixel ID + token pair can't be saved; the message is shown to the merchant."""


@dataclass(frozen=True)
class ShopMarket:
    """A Market as the Admin API reports it, with its ID normalised to the numeric tail."""

    shopify_market_id: int
    name: str
    market_type: str
    status: str
    regions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PixelCheck:
    """The outcome of Check with Meta (``GET /<pixel>`` with the token)."""

    ok: bool
    pixel_name: str | None = None
    owner_name: str | None = None
    error: str | None = None


def numeric_market_id(gid_or_id: str | int) -> int:
    """``gid://shopify/Market/123`` (Admin API, checkout) and ``123`` (Liquid,
    webhooks) both become ``123`` (spec §2)."""
    return int(str(gid_or_id).rsplit("/", 1)[-1])


def parse_market_node(node: dict[str, Any]) -> ShopMarket:
    regions_condition = (node.get("conditions") or {}).get("regionsCondition") or {}
    region_nodes = (regions_condition.get("regions") or {}).get("nodes") or []
    return ShopMarket(
        shopify_market_id=numeric_market_id(node["id"]),
        name=str(node.get("name") or ""),
        market_type=str(node.get("type") or "NONE"),
        status=str(node.get("status") or "ACTIVE"),
        regions=[str(r["name"]) for r in region_nodes if r.get("name")],
    )


def interpret_pixel_check(pixel_id: str, status_code: int, body: dict[str, Any]) -> PixelCheck:
    """Turn Meta's answer to ``GET /<pixel>?fields=id,name,owner_business,is_unavailable``
    into a pass or a merchant-readable failure."""
    error = body.get("error")
    if status_code >= 400 or error:
        message = (error or {}).get("message") if isinstance(error, dict) else None
        return PixelCheck(ok=False, error=f"Meta refused the check: {message or f'HTTP {status_code}'}")
    if str(body.get("id")) != pixel_id:
        return PixelCheck(ok=False, error="Meta didn't return this pixel. Check the pixel ID.")
    if body.get("is_unavailable"):
        return PixelCheck(ok=False, error="Meta reports this pixel as unavailable.")
    owner = body.get("owner_business") or {}
    return PixelCheck(ok=True, pixel_name=body.get("name"), owner_name=owner.get("name"))


@dataclass(frozen=True)
class PixelView:
    """A Market Pixel as the admin sees it. The token never leaves the backend."""

    pixel_id: str
    pixel_name: str | None
    test_event_code: str | None
    token_state: str
    has_token: bool


@dataclass(frozen=True)
class MarketView:
    shopify_market_id: int
    name: str
    market_type: str
    status: str
    regions: list[str]
    first_seen_at: datetime
    is_new: bool
    pixel: PixelView | None


FetchMarkets = Callable[[Tenant], list[ShopMarket]]
CheckPixel = Callable[[str, str], PixelCheck]


class MarketService:
    def __init__(
        self,
        db: Session,
        *,
        fetch_markets: FetchMarkets | None = None,
        check_pixel: CheckPixel | None = None,
        cipher: TokenCipher | None = None,
    ) -> None:
        self.db = db
        self._fetch_markets = fetch_markets
        self._check_pixel = check_pixel
        self._cipher = cipher

    # --- Markets ----------------------------------------------------------------
    def sync(self, tenant: Tenant) -> list[MarketView]:
        """Re-fetch the shop's Markets and make the stored list match. A Market that
        is gone takes its Market Pixel with it (spec §5)."""
        fetched = {m.shopify_market_id: m for m in self._fetcher()(tenant)}
        if not fetched:
            # Every shop has its primary Market; an empty answer must not unmap them all.
            raise RuntimeError("Shopify returned no Markets; keeping the stored list")
        stored = {m.shopify_market_id: m for m in self._markets(tenant)}
        first_sync = not stored

        # An upsert, because the install job and the app-open sync can run at once.
        for market_id, shop_market in fetched.items():
            values = {
                "name": shop_market.name,
                "market_type": shop_market.market_type,
                "status": shop_market.status,
                "regions": list(shop_market.regions),
            }
            self.db.execute(
                pg_insert(Market)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    shopify_market_id=market_id,
                    added_after_first_sync=not first_sync,
                    first_seen_at=datetime.now(UTC),
                    **values,
                )
                .on_conflict_do_update(constraint="uq_markets_tenant_market", set_=values)
            )

        gone = [market_id for market_id in stored if market_id not in fetched]
        unmapped = 0
        if gone:
            unmapped = self.db.execute(
                delete(MarketPixel).where(MarketPixel.tenant_id == tenant.id, MarketPixel.shopify_market_id.in_(gone))
            ).rowcount
            self.db.execute(delete(Market).where(Market.tenant_id == tenant.id, Market.shopify_market_id.in_(gone)))
        self.db.commit()
        logger.info(
            "markets.synced",
            {"tenantId": str(tenant.id), "markets": len(fetched), "added": len(fetched.keys() - stored.keys()),
             "removed": len(gone)},
        )
        if unmapped:
            queue_publish(self.db, tenant.id)
        return self.list_markets(tenant)

    def list_markets(self, tenant: Tenant) -> list[MarketView]:
        pixels = {p.shopify_market_id: p for p in self._pixels(tenant)}
        markets = sorted(self._markets(tenant), key=lambda m: (m.market_type != "REGION", m.name.lower()))
        return [self._view(m, pixels.get(m.shopify_market_id)) for m in markets]

    # --- the Pixel Mapping ----------------------------------------------------------
    def check_pixel(self, tenant: Tenant, market_id: int, *, pixel_id: str, token: str | None) -> PixelCheck:
        """Check with Meta. Without a new token, the Market's stored one is used."""
        self._market(tenant, market_id)
        pixel_id = _valid_pixel_id(pixel_id)
        existing = self._pixel(tenant, market_id)
        return self._checker()(pixel_id, self._token_to_use(existing, token))

    def save_pixel(
        self,
        tenant: Tenant,
        market_id: int,
        *,
        pixel_id: str,
        token: str | None,
        test_event_code: str | None = None,
    ) -> MarketView:
        """Map the Market. Both halves of the pair are required and must pass Check
        with Meta here, whatever the UI did (spec §4)."""
        market = self._market(tenant, market_id)
        pixel_id = _valid_pixel_id(pixel_id)
        existing = self._pixel(tenant, market_id)
        token_to_use = self._token_to_use(existing, token)
        check = self._checker()(pixel_id, token_to_use)
        if not check.ok:
            raise PixelValidationError(check.error or "Meta didn't accept this pixel ID and token.")

        row = existing or MarketPixel(tenant_id=tenant.id, shopify_market_id=market_id)
        row.pixel_id = pixel_id
        row.pixel_name = check.pixel_name
        row.test_event_code = (test_event_code or "").strip() or None
        if (token or "").strip():
            row.capi_token_encrypted = self._cipher_or_default().encrypt(token_to_use)
        row.token_state = TokenState.OK
        self.db.add(row)
        self.db.commit()
        logger.info("markets.pixel_saved", {"tenantId": str(tenant.id), "marketId": market_id, "pixelId": pixel_id})
        queue_publish(self.db, tenant.id)
        return self._view(market, row)

    def remove_pixel(self, tenant: Tenant, market_id: int) -> MarketView:
        market = self._market(tenant, market_id)
        self.db.execute(
            delete(MarketPixel).where(MarketPixel.tenant_id == tenant.id, MarketPixel.shopify_market_id == market_id)
        )
        self.db.commit()
        logger.info("markets.pixel_removed", {"tenantId": str(tenant.id), "marketId": market_id})
        queue_publish(self.db, tenant.id)
        return self._view(market, None)

    # --- internals ------------------------------------------------------------------
    def _token_to_use(self, existing: MarketPixel | None, token: str | None) -> str:
        token = (token or "").strip()
        if token:
            return token
        if existing is None or not existing.capi_token_encrypted:
            raise PixelValidationError("Paste the Conversions API token. Every mapped Market needs one.")
        if existing.token_state == TokenState.REJECTED:
            raise PixelValidationError("Meta rejected the saved token. Paste a new one.")
        return self._cipher_or_default().decrypt(existing.capi_token_encrypted)

    def _view(self, market: Market, pixel: MarketPixel | None) -> MarketView:
        is_new = (
            pixel is None
            and market.added_after_first_sync
            and market.first_seen_at is not None
            and market.first_seen_at > datetime.now(UTC) - NEW_MARKET_WINDOW
        )
        return MarketView(
            shopify_market_id=market.shopify_market_id,
            name=market.name,
            market_type=market.market_type,
            status=market.status,
            regions=list(market.regions or []),
            first_seen_at=market.first_seen_at,
            is_new=is_new,
            pixel=None
            if pixel is None
            else PixelView(
                pixel_id=pixel.pixel_id,
                pixel_name=pixel.pixel_name,
                test_event_code=pixel.test_event_code,
                token_state=pixel.token_state.value,
                has_token=bool(pixel.capi_token_encrypted),
            ),
        )

    def _markets(self, tenant: Tenant) -> list[Market]:
        return list(self.db.scalars(select(Market).where(Market.tenant_id == tenant.id)))

    def _pixels(self, tenant: Tenant) -> list[MarketPixel]:
        return list(self.db.scalars(select(MarketPixel).where(MarketPixel.tenant_id == tenant.id)))

    def _market(self, tenant: Tenant, market_id: int) -> Market:
        market = self.db.scalar(
            select(Market).where(Market.tenant_id == tenant.id, Market.shopify_market_id == market_id)
        )
        if market is None:
            raise LookupError(f"Market {market_id} isn't one of this shop's Markets")
        return market

    def _pixel(self, tenant: Tenant, market_id: int) -> MarketPixel | None:
        return self.db.scalar(
            select(MarketPixel).where(MarketPixel.tenant_id == tenant.id, MarketPixel.shopify_market_id == market_id)
        )

    def _fetcher(self) -> FetchMarkets:
        if self._fetch_markets is None:
            from app.services.shopify_markets_client import fetch_shop_markets

            self._fetch_markets = fetch_shop_markets
        return self._fetch_markets

    def _checker(self) -> CheckPixel:
        if self._check_pixel is None:
            from app.services.meta_pixel_client import check_pixel_with_meta

            self._check_pixel = check_pixel_with_meta
        return self._check_pixel

    def _cipher_or_default(self) -> TokenCipher:
        if self._cipher is None:
            from app.services.token_cipher import token_cipher_from_settings

            self._cipher = token_cipher_from_settings()
        return self._cipher


def _valid_pixel_id(pixel_id: str) -> str:
    pixel_id = re.sub(r"\s", "", pixel_id or "")
    if not PIXEL_ID.match(pixel_id):
        raise PixelValidationError("A pixel ID is 15 or 16 digits. Copy it from Events Manager → Data sources.")
    return pixel_id
