"""Send stored Server Events to the Conversions API (spec §3.2 step 3).

Each due event goes to ``graph.facebook.com/v26.0/<pixel>/events`` with its
Market's token and optional test event code. A temporary failure retries on the
event backoff (1 min, 5 min, 30 min, 2 h, 6 h) and then fails. A token Meta
rejects pauses the Market's Server Events until the token is replaced
(``resume_paused``); events over 7 days old are past Meta's limit and fail.
Personal data (IP, user agent, cookies, hashed customer data) is dropped from an
event once it reaches a final state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.logging_config import get_logger
from app.models import MarketPixel, ServerEvent, ServerEventStatus, TokenState
from app.services.token_cipher import TokenCipher, TokenDecryptError

logger = get_logger().child({"component": "server_event_sender"})

META_EVENT_MAX_AGE = timedelta(days=7)
# Meta's codes for a token that can't be used (expired, revoked, wrong permissions).
TOKEN_ERROR_CODES = frozenset({102, 190})
# Subcode 33 is "object does not exist, cannot be loaded due to missing permissions":
# the token can't send to this pixel, so every event would fail the same way.
UNREACHABLE_PIXEL_SUBCODE = 33
UNREACHABLE_PIXEL_MESSAGE = (
    "This token can't send to this pixel. Check the pixel ID, or generate the token from this pixel's settings."
)
TOKEN_ERROR_SUBCODES = frozenset({UNREACHABLE_PIXEL_SUBCODE, 458, 459, 460, 463, 464, 467})
# Meta's codes for "try again later" (unknown, service, rate limits).
TRANSIENT_ERROR_CODES = frozenset({1, 2, 4, 17, 32, 341, 613})
FINAL_STATES = (ServerEventStatus.SENT, ServerEventStatus.FAILED, ServerEventStatus.REJECTED, ServerEventStatus.SKIPPED)


@dataclass(frozen=True)
class MetaAnswer:
    status: int  # 0 when Meta couldn't be reached
    body: dict[str, Any] = field(default_factory=dict)

    @property
    def error(self) -> dict[str, Any]:
        error = self.body.get("error")
        return error if isinstance(error, dict) else {}

    @property
    def detail(self) -> str:
        if 200 <= self.status < 300:
            received = self.body.get("events_received")
            return f"events_received: {received}" if received is not None else "accepted"
        message = self.error.get("message") or (f"HTTP {self.status}" if self.status else "Meta couldn't be reached")
        code = self.error.get("code")
        return f"{message} (code {code})" if code is not None else str(message)


PostEvents = Callable[[str, dict[str, Any]], MetaAnswer]


def _classify(answer: MetaAnswer) -> str:
    """"sent" | "token" | "retry" | "rejected"."""
    if 200 <= answer.status < 300:
        return "sent"
    code, subcode = answer.error.get("code"), answer.error.get("error_subcode")
    if code in TOKEN_ERROR_CODES or subcode in TOKEN_ERROR_SUBCODES:
        return "token"
    if answer.status in (0, 429) or answer.status >= 500 or code in TRANSIENT_ERROR_CODES:
        return "retry"
    return "rejected"


def strip_personal_data(event: ServerEvent) -> None:
    payload = dict(event.payload or {})
    if isinstance(payload.get("event"), dict):
        payload["event"] = {**payload["event"], "user_data": {}}
    event.payload = payload


class ServerEventSender:
    def __init__(
        self,
        db: Session,
        *,
        post: PostEvents | None = None,
        cipher: TokenCipher | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.db = db
        if post is None:
            from app.services.meta_pixel_client import post_events

            post = post_events
        self._post = post
        self._cipher = cipher
        self._now = now or (lambda: datetime.now(UTC))
        self._schedule = get_settings().job_retry_schedule_seconds

    def send_due(self, limit: int = 100) -> int:
        """Send up to ``limit`` due events; returns how many were handled. Each event
        is locked, sent and committed in its own transaction, so a second sender
        never gets it, and one broken event can't hold up the rest."""
        now = self._now()
        handled = 0
        while handled < limit:
            event = self.db.scalars(
                select(ServerEvent)
                .where(
                    ServerEvent.status == ServerEventStatus.RECEIVED,
                    or_(ServerEvent.next_attempt_at.is_(None), ServerEvent.next_attempt_at <= now),
                )
                .order_by(ServerEvent.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            ).first()
            if event is None:
                break
            try:
                self._send(event, now)
                self.db.commit()
            except Exception as exc:  # noqa: BLE001 — fail this event, keep the queue moving
                self.db.rollback()
                self._fail_broken(event.id, exc)
            handled += 1
        return handled

    def _fail_broken(self, event_id, exc: Exception) -> None:
        event = self.db.get(ServerEvent, event_id)
        if event is not None:
            event.status = ServerEventStatus.FAILED
            event.next_attempt_at = None
            event.meta_response = {"detail": f"Couldn't be sent: {exc.__class__.__name__}"}
            event.payload = {}
            self.db.commit()
        logger.error("server_event.broken", exc, {"eventId": str(event_id)})

    def _send(self, event: ServerEvent, now: datetime) -> None:
        pixel = self.db.scalar(
            select(MarketPixel).where(
                MarketPixel.tenant_id == event.tenant_id, MarketPixel.shopify_market_id == event.shopify_market_id
            )
        )
        if pixel is None or pixel.pixel_id != event.pixel_id:
            return self._finish(event, ServerEventStatus.SKIPPED, "The Market's pixel was removed or changed")
        if event.created_at and now - event.created_at > META_EVENT_MAX_AGE:
            return self._finish(event, ServerEventStatus.FAILED, "Older than 7 days, past Meta's limit")
        if pixel.token_state == TokenState.REJECTED or not pixel.capi_token_encrypted:
            event.status = ServerEventStatus.PAUSED
            event.meta_response = {"detail": "Waiting for a new Conversions API token"}
            return None
        try:
            token = self._cipher_or_default().decrypt(pixel.capi_token_encrypted)
        except TokenDecryptError:
            return self._reject_token(event, pixel, "The stored token can't be decrypted. Paste it again.")

        body: dict[str, Any] = {"data": [event.payload.get("event") or {}], "access_token": token}
        if pixel.test_event_code:
            body["test_event_code"] = pixel.test_event_code
        answer = self._post(pixel.pixel_id, body)
        event.attempt_count += 1
        outcome = _classify(answer)
        if outcome == "sent":
            self._finish(event, ServerEventStatus.SENT, answer.detail)
        elif outcome == "token":
            unreachable = answer.error.get("error_subcode") == UNREACHABLE_PIXEL_SUBCODE
            self._reject_token(event, pixel, UNREACHABLE_PIXEL_MESSAGE if unreachable else answer.detail)
        elif outcome == "rejected":
            self._finish(event, ServerEventStatus.REJECTED, answer.detail)
        elif event.attempt_count > len(self._schedule):
            self._finish(event, ServerEventStatus.FAILED, answer.detail)
        else:
            event.next_attempt_at = now + timedelta(seconds=self._schedule[event.attempt_count - 1])
            event.meta_response = {"detail": answer.detail}
        logger.info(
            "server_event.attempt",
            {"tenantId": str(event.tenant_id), "eventId": event.event_id, "outcome": outcome, "status": answer.status},
        )
        return None

    def _finish(self, event: ServerEvent, status: ServerEventStatus, detail: str) -> None:
        event.status = status
        event.next_attempt_at = None
        event.meta_response = {"detail": detail}
        strip_personal_data(event)

    def _reject_token(self, event: ServerEvent, pixel: MarketPixel, detail: str) -> None:
        """Pause the Market's Server Events; Browser Events carry on (spec §3.2)."""
        pixel.token_state = TokenState.REJECTED
        pixel.token_error = detail
        event.status = ServerEventStatus.PAUSED
        event.meta_response = {"detail": detail}
        self.db.execute(
            update(ServerEvent)
            .where(
                ServerEvent.tenant_id == event.tenant_id,
                ServerEvent.shopify_market_id == event.shopify_market_id,
                ServerEvent.status == ServerEventStatus.RECEIVED,
            )
            .values(status=ServerEventStatus.PAUSED, meta_response={"detail": "Waiting for a new Conversions API token"})
        )
        logger.warn("server_event.token_rejected", {"tenantId": str(event.tenant_id), "marketId": event.shopify_market_id})

    def _cipher_or_default(self) -> TokenCipher:
        if self._cipher is None:
            from app.services.token_cipher import token_cipher_from_settings

            self._cipher = token_cipher_from_settings()
        return self._cipher


def resume_paused(db: Session, tenant_id, market_id: int, now: datetime | None = None) -> int:
    """A replaced token: paused events under 7 days old go back in the queue; older
    ones are past Meta's limit and fail. Returns how many were resumed."""
    now = now or datetime.now(UTC)
    paused = db.scalars(
        select(ServerEvent).where(
            ServerEvent.tenant_id == tenant_id,
            ServerEvent.shopify_market_id == market_id,
            ServerEvent.status == ServerEventStatus.PAUSED,
        )
    ).all()
    resumed = 0
    for event in paused:
        if event.created_at and now - event.created_at > META_EVENT_MAX_AGE:
            event.status = ServerEventStatus.FAILED
            event.meta_response = {"detail": "Older than 7 days when the token was replaced"}
            strip_personal_data(event)
        else:
            event.status = ServerEventStatus.RECEIVED
            event.next_attempt_at = None
            resumed += 1
    return resumed


def expire_paused(db: Session, now: datetime | None = None) -> int:
    """Daily: paused events past Meta's 7-day limit can never be sent."""
    now = now or datetime.now(UTC)
    old = db.scalars(
        select(ServerEvent).where(
            ServerEvent.status == ServerEventStatus.PAUSED, ServerEvent.created_at < now - META_EVENT_MAX_AGE
        )
    ).all()
    for event in old:
        event.status = ServerEventStatus.FAILED
        event.meta_response = {"detail": "Older than 7 days; the token was never replaced"}
        strip_personal_data(event)
    db.commit()
    return len(old)
