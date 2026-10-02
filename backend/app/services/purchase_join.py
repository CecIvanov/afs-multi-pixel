"""The Purchase join (spec §3.2 step 4): the relayed browser Purchase (Market,
consent, cookies) and the orders/create webhook (hashed customer data) meet in
``PendingPurchase`` by order ID, whichever arrives first. Once both are in, the
Server Purchase is queued with event ID ``purchase-<orderId>``. No browser
Purchase (no marketing consent) means no Server Purchase; an unmatched half
expires after 7 days. Raw customer data is hashed before it is stored.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import (
    MarketPixel,
    PendingPurchase,
    ServerEvent,
    ServerEventSource,
    ServerEventStatus,
    Tenant,
    purchase_event_id,
)

logger = get_logger().child({"component": "purchase_join"})

PENDING_PURCHASE_TTL = timedelta(days=7)


# --- hashing (Meta's normalisation rules, then SHA-256) -----------------------------
def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hashed(value: Any, normalise) -> str | None:
    normalised = normalise(str(value)) if value not in (None, "") else ""
    return _sha256(normalised) if normalised else None


_lower = lambda v: v.strip().lower()  # noqa: E731
_letters = lambda v: re.sub(r"[^\w]|[\d_]", "", v.lower())  # noqa: E731
_digits = lambda v: re.sub(r"\D", "", v)  # noqa: E731
_no_spaces = lambda v: re.sub(r"\s", "", v.lower())  # noqa: E731


def hash_order_customer(order: dict[str, Any]) -> dict[str, str]:
    """Meta's customer information parameters from an orders/create payload,
    normalised and hashed. Nothing raw survives this function."""
    address = order.get("billing_address") or order.get("shipping_address") or {}
    customer = order.get("customer") or {}
    hashed = {
        "em": _hashed(order.get("email") or order.get("contact_email") or customer.get("email"), _lower),
        "ph": _hashed(order.get("phone") or address.get("phone") or customer.get("phone"), _digits),
        "fn": _hashed(address.get("first_name") or customer.get("first_name"), _lower),
        "ln": _hashed(address.get("last_name") or customer.get("last_name"), _lower),
        "ct": _hashed(address.get("city"), _letters),
        "st": _hashed(address.get("province_code"), _lower),
        "zp": _hashed(address.get("zip"), _no_spaces),
        "country": _hashed(address.get("country_code"), _lower),
        "external_id": _hashed(customer.get("id"), _lower),
    }
    return {k: v for k, v in hashed.items() if v}


def order_custom_data(order: dict[str, Any]) -> dict[str, Any]:
    """The Purchase's custom data in the Official Meta App's shape: product IDs as
    ``content_ids`` with ``content_type: product_group``, the presentment total."""
    items = order.get("line_items") or []
    presentment = ((order.get("total_price_set") or {}).get("presentment_money")) or {}
    product_ids = list(dict.fromkeys(str(i["product_id"]) for i in items if i.get("product_id")))
    value = presentment.get("amount") or order.get("total_price")
    data = {
        "content_ids": product_ids,
        "content_type": "product_group",
        "value": float(value) if value not in (None, "") else None,
        "currency": presentment.get("currency_code") or order.get("presentment_currency") or order.get("currency"),
        "num_items": sum(int(i.get("quantity") or 0) for i in items),
        "order_id": str(order.get("id")),
    }
    return {k: v for k, v in data.items() if v not in (None, "", [])}


def _order_event_time(order: dict[str, Any]) -> int | None:
    try:
        return int(datetime.fromisoformat(str(order["created_at"]).replace("Z", "+00:00")).timestamp())
    except (KeyError, ValueError):
        return None


class PurchaseJoin:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record_browser_purchase(
        self, tenant: Tenant, payload: dict[str, Any], meta_event: dict[str, Any], pixel: MarketPixel
    ) -> None:
        order_id = _order_id(payload.get("orderId") or (payload.get("customData") or {}).get("order_id"))
        if order_id is None:
            self.db.add(_purchase_row(tenant, "-", pixel, {}, ServerEventStatus.REJECTED, "Purchase without an order ID"))
            self.db.commit()
            return
        event_id = purchase_event_id(order_id)
        existing = self._event(tenant, event_id)
        if existing is not None and existing.status != ServerEventStatus.WAITING:
            # Already joined (e.g. the thank-you page reloaded): nothing more to keep.
            return
        meta_event = {**meta_event, "event_id": event_id}
        self._upsert_pending(tenant, order_id, browser_half={"event": meta_event, "market_id": pixel.shopify_market_id})
        if existing is None:
            self.db.add(
                _purchase_row(
                    tenant, event_id, pixel, {"event": meta_event}, ServerEventStatus.WAITING, "Waiting for the order webhook"
                )
            )
        self.db.commit()
        self._join(tenant, order_id)

    def record_order(self, tenant: Tenant, order: dict[str, Any]) -> None:
        order_id = _order_id(order.get("id"))
        if order_id is None:
            return
        self._upsert_pending(
            tenant,
            order_id,
            hashed_customer_data={
                "user_data": hash_order_customer(order),
                "custom_data": order_custom_data(order),
                "event_time": _order_event_time(order),
                "order_number": str(order.get("order_number") or "")[:32] or None,
            },
        )
        self.db.commit()
        self._join(tenant, order_id)

    def _join(self, tenant: Tenant, order_id: int) -> None:
        pending = self.db.scalar(
            select(PendingPurchase)
            .where(PendingPurchase.tenant_id == tenant.id, PendingPurchase.order_id == order_id)
            .with_for_update()
        )
        if pending is None or not pending.browser_half or not pending.hashed_customer_data:
            self.db.commit()
            return
        event_id = purchase_event_id(order_id)
        row = self._event(tenant, event_id)
        browser_event = pending.browser_half["event"]
        order_half = pending.hashed_customer_data
        joined = {
            **browser_event,
            "event_id": event_id,
            "user_data": {**(browser_event.get("user_data") or {}), **order_half["user_data"]},
            "custom_data": {**(browser_event.get("custom_data") or {}), **order_half["custom_data"]},
        }
        if order_half.get("event_time"):
            joined["event_time"] = order_half["event_time"]
        if row is not None and row.status == ServerEventStatus.WAITING:
            row.payload = {"event": joined}
            row.status = ServerEventStatus.RECEIVED
            row.meta_response = None
            row.source = ServerEventSource.WEBHOOK
            row.order_number = order_half.get("order_number")
        # The pending row has done its job; keep no customer data around.
        self.db.execute(delete(PendingPurchase).where(PendingPurchase.id == pending.id))
        self.db.commit()
        logger.info("purchase.joined", {"tenantId": str(tenant.id), "orderId": order_id})

    def _upsert_pending(self, tenant: Tenant, order_id: int, **values: Any) -> None:
        self.db.execute(
            pg_insert(PendingPurchase)
            .values(tenant_id=tenant.id, order_id=order_id, created_at=datetime.now(UTC), **values)
            .on_conflict_do_update(constraint="uq_pending_purchases_tenant_order", set_=values)
        )

    def _event(self, tenant: Tenant, event_id: str) -> ServerEvent | None:
        return self.db.scalar(
            select(ServerEvent).where(ServerEvent.tenant_id == tenant.id, ServerEvent.event_id == event_id).limit(1)
        )


def _purchase_row(
    tenant: Tenant, event_id: str, pixel: MarketPixel, payload: dict, status: ServerEventStatus, detail: str
) -> ServerEvent:
    return ServerEvent(
        tenant_id=tenant.id,
        source=ServerEventSource.RELAY,
        event_name="Purchase",
        event_id=event_id,
        shopify_market_id=pixel.shopify_market_id,
        pixel_id=pixel.pixel_id,
        marketing_consent=True,
        payload=payload,
        status=status,
        meta_response={"detail": detail},
    )


def _order_id(value: Any) -> int | None:
    from app.services.relay_service import numeric_id

    return numeric_id(value)


def expire_pending_purchases(db: Session, now: datetime | None = None) -> int:
    """Daily: an unmatched half after 7 days will never be joined. A browser
    Purchase still waiting for its order webhook is marked failed in the log."""
    now = now or datetime.now(UTC)
    cutoff = now - PENDING_PURCHASE_TTL
    expired = db.scalars(select(PendingPurchase).where(PendingPurchase.created_at < cutoff)).all()
    for pending in expired:
        waiting = db.scalar(
            select(ServerEvent).where(
                ServerEvent.tenant_id == pending.tenant_id,
                ServerEvent.event_id == purchase_event_id(pending.order_id),
                ServerEvent.status == ServerEventStatus.WAITING,
            )
        )
        if waiting is not None:
            waiting.status = ServerEventStatus.FAILED
            waiting.meta_response = {"detail": "No order webhook within 7 days"}
            waiting.payload = {}
        db.delete(pending)
    db.commit()
    return len(expired)
