"""Receive a Relay (spec §3.2): decrypt, validate, store, answer. Nothing is sent
from here; the worker (server_event_sender) sends what is stored.

Refused: an envelope this app can't open, an unknown or uninstalled shop, an
Origin that isn't one of the shop's storefronts, an event outside the Standard
Funnel, and a Market → pixel pair that isn't in the Pixel Mapping. Refusals for a
known shop are stored as ``rejected`` rows so the event log shows them.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.logging_config import get_logger
from app.models import (
    MarketPixel,
    ServerEvent,
    ServerEventSource,
    ServerEventStatus,
    Tenant,
    TenantStatus,
    TokenState,
)
from app.services.relay_crypto import RelayDecryptError, decrypt_envelope, relay_key_pair
from app.services.tenant_service import TenantService
from app.services.token_cipher import TokenCipher

logger = get_logger().child({"component": "relay"})

STANDARD_FUNNEL = frozenset(
    {"PageView", "ViewContent", "Search", "AddToCart", "InitiateCheckout", "AddPaymentInfo", "Purchase"}
)
CUSTOM_DATA_KEYS = frozenset(
    {"content_ids", "content_type", "content_name", "content_category", "value", "currency", "num_items",
     "search_string", "order_id"}
)
MAX_EVENT_AGE_SECONDS = 7 * 24 * 3600


@dataclass(frozen=True)
class RelayContext:
    origin: str | None
    ip: str | None
    user_agent: str | None


class RateLimiter(Protocol):
    def allow(self, *, ip: str | None, shop: str) -> bool: ...


class InMemoryRateLimiter:
    """Fixed one-minute windows in this process; for tests and a single API worker."""

    def __init__(self, per_ip: int | None = None, per_shop: int | None = None) -> None:
        s = get_settings()
        self.per_ip = per_ip or s.relay_rate_limit_per_ip
        self.per_shop = per_shop or s.relay_rate_limit_per_shop
        self._counts: dict[str, int] = defaultdict(int)

    def allow(self, *, ip: str | None, shop: str) -> bool:
        window = int(time.time() // 60)
        keys = [(f"shop:{shop}:{window}", self.per_shop)]
        if ip:
            keys.append((f"ip:{ip}:{window}", self.per_ip))
        for key, _ in keys:
            self._counts[key] += 1
        return all(self._counts[key] <= limit for key, limit in keys)


class RedisRateLimiter:
    """Fixed one-minute windows shared by every API worker. If Redis is down the
    Relay is let through: losing conversions is worse than a brief burst."""

    def __init__(self) -> None:
        import redis

        s = get_settings()
        self._redis = redis.Redis.from_url(s.redis_url, socket_timeout=0.5, socket_connect_timeout=0.5)
        self._prefix = f"{s.celery_redis_key_prefix}relay:"
        self.per_ip, self.per_shop = s.relay_rate_limit_per_ip, s.relay_rate_limit_per_shop

    def allow(self, *, ip: str | None, shop: str) -> bool:
        window = int(time.time() // 60)
        keys = [(f"{self._prefix}shop:{shop}:{window}", self.per_shop)]
        if ip:
            keys.append((f"{self._prefix}ip:{ip}:{window}", self.per_ip))
        try:
            pipe = self._redis.pipeline()
            for key, _ in keys:
                pipe.incr(key)
                pipe.expire(key, 120)
            counts = pipe.execute()[::2]
        except Exception as exc:  # noqa: BLE001
            logger.warn("relay.rate_limit_unavailable", {"detail": str(exc)[:200]})
            return True
        return all(count <= limit for count, (_, limit) in zip(counts, keys))


def event_time_seconds(ms: Any, now: float | None = None) -> int:
    """Meta refuses events from the future or older than 7 days; those get 'now'."""
    current = int(now if now is not None else time.time())
    try:
        seconds = int(float(ms) / 1000)
    except (TypeError, ValueError):
        return current
    return current if seconds > current or current - seconds > MAX_EVENT_AGE_SECONDS else seconds


def _without_empty(values: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in values.items() if v not in (None, "", [])}


def meta_event(payload: dict[str, Any], ctx: RelayContext) -> dict[str, Any]:
    """The Conversions API event for a Relay: same name and event ID as the
    Browser Event, the shopper's IP, user agent and Meta cookies."""
    custom = payload.get("customData") if isinstance(payload.get("customData"), dict) else {}
    return _without_empty(
        {
            "event_name": payload["event"],
            "event_id": str(payload["eventId"]),
            "event_time": event_time_seconds(payload.get("eventTime")),
            "event_source_url": payload.get("url"),
            "action_source": "website",
            "user_data": _without_empty(
                {
                    "client_ip_address": ctx.ip,
                    "client_user_agent": ctx.user_agent,
                    "fbp": payload.get("fbp"),
                    "fbc": payload.get("fbc"),
                }
            ),
            "custom_data": _without_empty({k: v for k, v in custom.items() if k in CUSTOM_DATA_KEYS}),
        }
    )


def _host(origin: str) -> str:
    try:
        return (urlparse(origin).hostname or "").lower()
    except ValueError:
        return ""


def numeric_id(value: Any) -> int | None:
    """``gid://shopify/Market/1``, ``"1"`` and ``1`` all give 1; anything else None."""
    try:
        return int(str(value).rsplit("/", 1)[-1])
    except (TypeError, ValueError):
        return None


class RelayService:
    def __init__(self, db: Session, *, cipher: TokenCipher | None = None, limiter: RateLimiter | None = None) -> None:
        self.db = db
        self._cipher = cipher
        self._limiter = limiter

    def receive(self, body: str, ctx: RelayContext) -> str:
        """Returns "stored", "rejected" or "limited"."""
        try:
            payload = decrypt_envelope(body, relay_key_pair(self.db, self._cipher_or_default()).private_key)
        except RelayDecryptError as exc:
            logger.info("relay.rejected", {"reason": "decrypt", "detail": str(exc), "origin": ctx.origin})
            return "rejected"

        shop = str(payload.get("shop") or "")
        tenant = TenantService(self.db).get_tenant_by_shop_domain(shop) if shop else None
        if tenant is None or tenant.status != TenantStatus.ACTIVE:
            logger.info("relay.rejected", {"reason": "unknown_shop", "shop": shop[:255], "origin": ctx.origin})
            return "rejected"
        if tenant.subscription_active is False:
            logger.info("relay.rejected", {"reason": "no_subscription", "shop": tenant.shop_domain})
            return "rejected"
        if not self._limiter_or_default().allow(ip=ctx.ip, shop=tenant.shop_domain):
            logger.info("relay.limited", {"shop": tenant.shop_domain, "ip": ctx.ip})
            return "limited"

        refusal = self._refusal(tenant, payload, ctx)
        if refusal:
            return self._reject(tenant, payload, refusal)

        market_id = numeric_id(payload["marketId"])
        pixel = self.db.scalar(
            select(MarketPixel).where(MarketPixel.tenant_id == tenant.id, MarketPixel.shopify_market_id == market_id)
        )
        if pixel is None or pixel.pixel_id != str(payload.get("pixelId")):
            return self._reject(tenant, payload, "This Market → pixel pair isn't in the Pixel Mapping")

        if payload["event"] == "Purchase":
            from app.services.purchase_join import PurchaseJoin

            PurchaseJoin(self.db).record_browser_purchase(tenant, payload, meta_event(payload, ctx), pixel)
            return "stored"

        paused = pixel.token_state == TokenState.REJECTED or not pixel.capi_token_encrypted
        self.db.add(
            ServerEvent(
                tenant_id=tenant.id,
                source=ServerEventSource.RELAY,
                event_name=payload["event"],
                event_id=str(payload["eventId"])[:255],
                shopify_market_id=market_id,
                pixel_id=pixel.pixel_id,
                marketing_consent=True,  # the storefront relays only with marketing consent
                payload={"event": meta_event(payload, ctx)},
                status=ServerEventStatus.PAUSED if paused else ServerEventStatus.RECEIVED,
                meta_response={"detail": "Waiting for a new Conversions API token"} if paused else None,
            )
        )
        self.db.commit()
        return "stored"

    def _refusal(self, tenant: Tenant, payload: dict[str, Any], ctx: RelayContext) -> str | None:
        origin = (ctx.origin or "").strip()
        # The strict Web Pixel runs in a sandbox whose requests carry no Origin or "null".
        if origin and origin != "null" and _host(origin) not in {h.lower() for h in tenant.storefront_hosts or []}:
            return f"Origin {origin[:100]} isn't a storefront of this shop"
        if payload.get("event") not in STANDARD_FUNNEL:
            return "Not a Standard Funnel event"
        if not payload.get("eventId") or numeric_id(payload.get("marketId")) is None:
            return "Malformed event"
        return None

    def _reject(self, tenant: Tenant, payload: dict[str, Any], reason: str) -> str:
        self.db.add(
            ServerEvent(
                tenant_id=tenant.id,
                source=ServerEventSource.RELAY,
                event_name=str(payload.get("event") or "?")[:64],
                event_id=str(payload.get("eventId") or "-")[:255],
                shopify_market_id=numeric_id(payload.get("marketId")) or 0,
                pixel_id=str(payload.get("pixelId") or "")[:32],
                marketing_consent=True,
                payload={},
                status=ServerEventStatus.REJECTED,
                meta_response={"detail": reason},
            )
        )
        self.db.commit()
        logger.info("relay.rejected", {"shop": tenant.shop_domain, "reason": reason})
        return "rejected"

    def _cipher_or_default(self) -> TokenCipher:
        if self._cipher is None:
            from app.services.token_cipher import token_cipher_from_settings

            self._cipher = token_cipher_from_settings()
        return self._cipher

    def _limiter_or_default(self) -> RateLimiter:
        if self._limiter is None:
            self._limiter = _shared_limiter()
        return self._limiter


_LIMITER: RateLimiter | None = None


def _shared_limiter() -> RateLimiter:
    global _LIMITER
    if _LIMITER is None:
        _LIMITER = RedisRateLimiter()
    return _LIMITER
