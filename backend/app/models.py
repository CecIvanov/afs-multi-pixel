"""SQLAlchemy models.

Phase 1 introduces the tenant + plan spine — the canonical record created when a
shop installs the app:

- ``Tenant``          identity + Shopify credentials + lifecycle status
- ``TenantMetadata``  per-tenant key/value store (captured shop profile)
- ``BillingPlan``     plan catalog (mirror of Partner-Dashboard plans)
- ``TenantSubscription``  which plan a tenant is on

Phase 2 adds ``WebhookEvent`` + the durable ``AsyncJob`` queue; Phase 3 extends
the billing tables (pending plan, trial, usage, subscription events).

AFS Multi Pixel adds its own tenant-scoped tables (spec §6): ``MarketPixel`` (the
Pixel Mapping, with encrypted Conversions API tokens), ``ServerEvent`` (the Server
Event queue + event log) and ``PendingPurchase`` (the Purchase join).
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import postgres_enum

__all__ = [
    "Base",
    "TenantStatus",
    "SubscriptionStatus",
    "Tenant",
    "TenantMetadata",
    "BillingPlan",
    "TenantSubscription",
    "UsageCounter",
    "BillingSubscriptionEventType",
    "BillingReconcileSource",
    "BillingSubscriptionEvent",
    "WebhookEventStatus",
    "WebhookEvent",
    "AsyncJobStatus",
    "AsyncJobOperation",
    "AsyncJob",
    "TokenState",
    "MarketPixel",
    "ServerEventSource",
    "ServerEventStatus",
    "ServerEvent",
    "purchase_event_id",
    "PendingPurchase",
]


class TenantStatus(str, enum.Enum):
    ACTIVE = "active"
    UNINSTALLED = "uninstalled"
    SUSPENDED = "suspended"


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    FROZEN = "frozen"
    PENDING = "pending"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shop_domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    shopify_shop_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)

    # Shopify offline token duplicated here (the Node/Prisma Session is the OAuth
    # store) so background workers read a fresh token straight from Postgres.
    access_token: Mapped[str | None] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refresh_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shopify_refresh_token_revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[str | None] = mapped_column(Text)

    status: Mapped[TenantStatus] = mapped_column(
        postgres_enum(TenantStatus, "tenant_status"),
        default=TenantStatus.ACTIVE,
        nullable=False,
    )
    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uninstalled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # UI language of the embedded admin app, chosen by the merchant.
    app_ui_locale: Mapped[str] = mapped_column(String(8), default="en", server_default="en", nullable=False)
    feature_flags: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False, server_default="{}")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    subscriptions: Mapped[list["TenantSubscription"]] = relationship(back_populates="tenant")
    metadata_items: Mapped[list["TenantMetadata"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )


class TenantMetadata(Base):
    """Row-per-key store for per-tenant facts (captured shop profile: name,
    contact email, phone, country, store plan). New facts need no migration."""

    __tablename__ = "tenants_metadata"
    __table_args__ = (UniqueConstraint("tenant_id", "m_key", name="uq_tenant_metadata_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    m_key: Mapped[str] = mapped_column(String(255), nullable=False)
    m_value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tenant: Mapped[Tenant] = relationship(back_populates="metadata_items")


class BillingPlan(Base):
    __tablename__ = "billing_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    handle: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Generic metered quota per billing period (NULL = unlimited).
    monthly_quota: Mapped[int | None] = mapped_column(Integer)
    shopify_plan_name: Mapped[str | None] = mapped_column(String(100))


class TenantSubscription(Base):
    __tablename__ = "tenant_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    billing_plan_id: Mapped[int] = mapped_column(ForeignKey("billing_plans.id"), nullable=False)
    # A scheduled downgrade parks the target here until the cycle ends (or applies
    # immediately during a trial — see the reconcile service).
    pending_billing_plan_id: Mapped[int | None] = mapped_column(ForeignKey("billing_plans.id"))
    shopify_subscription_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[SubscriptionStatus] = mapped_column(
        postgres_enum(SubscriptionStatus, "subscription_status"),
        default=SubscriptionStatus.ACTIVE,
        nullable=False,
    )
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Shopify trialEndsAt for the effective plan (NULL once converted / never had a
    # trial). Used to apply a downgrade immediately while still inside a trial.
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tenant: Mapped[Tenant] = relationship(back_populates="subscriptions")
    billing_plan: Mapped[BillingPlan] = relationship(foreign_keys=[billing_plan_id])
    pending_billing_plan: Mapped[BillingPlan | None] = relationship(foreign_keys=[pending_billing_plan_id])


class UsageCounter(Base):
    __tablename__ = "usage_counters"
    __table_args__ = (UniqueConstraint("tenant_id", "period_start", name="uq_usage_tenant_period"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quota: Mapped[int] = mapped_column(Integer, nullable=False)


class BillingSubscriptionEventType(str, enum.Enum):
    INITIAL_SELECTION = "initial_selection"
    UPGRADE = "upgrade"
    DOWNGRADE_SCHEDULED = "downgrade_scheduled"
    DOWNGRADE_EFFECTIVE = "downgrade_effective"
    CANCEL_SCHEDULED = "cancel_scheduled"
    CANCELLED_TO_FREE = "cancelled_to_free"
    SUBSCRIPTION_RENEWED = "subscription_renewed"


class BillingReconcileSource(str, enum.Enum):
    REDIRECT = "redirect"
    APP_LOAD = "app_load"
    BILLING_PAGE = "billing_page"
    SCHEDULED_WORKER = "scheduled_worker"


class BillingSubscriptionEvent(Base):
    """Append-only audit of every reconcile that changed subscription state."""

    __tablename__ = "billing_subscription_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    event_type: Mapped[BillingSubscriptionEventType] = mapped_column(
        postgres_enum(BillingSubscriptionEventType, "billing_subscription_event_type"), nullable=False
    )
    from_plan_handle: Mapped[str | None] = mapped_column(String(64))
    to_plan_handle: Mapped[str | None] = mapped_column(String(64))
    effective_plan_handle: Mapped[str] = mapped_column(String(64), nullable=False)
    pending_plan_handle: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[BillingReconcileSource] = mapped_column(
        postgres_enum(BillingReconcileSource, "billing_reconcile_source"), nullable=False
    )
    partner_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- Async webhook processing (Phase 2) -------------------------------------
class WebhookEventStatus(str, enum.Enum):
    RECEIVED = "received"
    PROCESSED = "processed"
    FAILED = "failed"


class AsyncJobStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AsyncJobOperation(str, enum.Enum):
    """The generic framework operations. Add your app's own operations here and
    register a handler in services/job_processors.py."""

    APP_UNINSTALL = "app_uninstall"
    SHOP_REDACT = "shop_redact"
    CUSTOMER_DATA_REQUEST = "customer_data_request"
    CUSTOMER_REDACT = "customer_redact"
    SCOPES_UPDATE = "scopes_update"
    SHOP_INFO_FETCH = "shop_info_fetch"
    # Proactively refresh a tenant's expiring Shopify offline token (see
    # services/shopify_token_refresh_service.py). Enqueued on a beat + on 401.
    TOKEN_REFRESH = "token_refresh"
    # orders/create: the Purchase join (handler lands with #9).
    ORDERS_CREATE = "orders_create"
    # markets/create|update|delete: re-fetch the shop's Markets (handler lands with #4).
    MARKETS_SYNC = "markets_sync"
    EXAMPLE_OP = "example_op"


class WebhookEvent(Base):
    """Delivery-level idempotency + audit. One row per Shopify webhook id, with the
    raw payload retained (purged on retention)."""

    __tablename__ = "webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenants.id"))
    topic: Mapped[str] = mapped_column(String(100), nullable=False)
    shopify_webhook_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[WebhookEventStatus] = mapped_column(
        postgres_enum(WebhookEventStatus, "webhook_event_status"),
        default=WebhookEventStatus.RECEIVED,
        nullable=False,
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AsyncJob(Base):
    """Durable DB-backed job queue. Idempotency at two layers: the WebhookEvent
    unique id (delivery-level) and this table's partial-unique pending-dedupe index
    (work-level). Claimed with FOR UPDATE SKIP LOCKED under per-tenant/global
    in-flight caps; retried on the event backoff schedule into a FAILED dead-letter; a
    stale-processing reaper requeues jobs orphaned by dead workers."""

    __tablename__ = "async_jobs"
    __table_args__ = (
        Index(
            "ix_async_jobs_pending_dedupe",
            "tenant_id",
            "operation",
            "dedupe_key",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_async_jobs_claim", "status", "priority", "created_at"),
        Index("ix_async_jobs_retention", "status", "finished_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    operation: Mapped[AsyncJobOperation] = mapped_column(
        postgres_enum(AsyncJobOperation, "async_job_operation"), nullable=False
    )
    topic: Mapped[str] = mapped_column(String(100), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    shopify_webhook_id: Mapped[str | None] = mapped_column(String(255))
    webhook_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("webhook_events.id", ondelete="SET NULL"), nullable=True
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[AsyncJobStatus] = mapped_column(
        postgres_enum(AsyncJobStatus, "async_job_status"),
        default=AsyncJobStatus.PENDING,
        nullable=False,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_by: Mapped[str | None] = mapped_column(String(255))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tenant: Mapped[Tenant] = relationship()


# --- AFS Multi Pixel ----------------------------------------------------------
class TokenState(str, enum.Enum):
    OK = "ok"
    REJECTED = "rejected"


class MarketPixel(Base):
    """The Pixel Mapping: one Market Pixel per Market. ``capi_token_encrypted`` is
    the Conversions API token as token_cipher ciphertext; it is NULL after
    app/uninstalled (tokens go at once, the rest waits for shop/redact)."""

    __tablename__ = "market_pixels"
    __table_args__ = (UniqueConstraint("tenant_id", "shopify_market_id", name="uq_market_pixels_tenant_market"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    shopify_market_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pixel_id: Mapped[str] = mapped_column(String(32), nullable=False)
    pixel_name: Mapped[str | None] = mapped_column(String(255))
    capi_token_encrypted: Mapped[str | None] = mapped_column(Text)
    test_event_code: Mapped[str | None] = mapped_column(String(64))
    token_state: Mapped[TokenState] = mapped_column(
        postgres_enum(TokenState, "token_state"), default=TokenState.OK, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ServerEventSource(str, enum.Enum):
    RELAY = "relay"
    WEBHOOK = "webhook"


class ServerEventStatus(str, enum.Enum):
    RECEIVED = "received"
    SENT = "sent"
    SKIPPED = "skipped"
    WAITING = "waiting"
    REJECTED = "rejected"
    FAILED = "failed"
    PAUSED = "paused"


def purchase_event_id(order_id: int | str) -> str:
    """The event ID a Purchase carries in the browser and on the server, so Meta
    deduplicates the two (spec §3.1)."""
    return f"purchase-{order_id}"


class ServerEvent(Base):
    """A Server Event: the queue and the event log. Holds no raw personal data.
    A Purchase's ``event_id`` is ``purchase_event_id(order_id)``, which is how
    customers/redact finds it."""

    __tablename__ = "server_events"
    __table_args__ = (
        Index("ix_server_events_tenant_event_id", "tenant_id", "event_id"),
        Index("ix_server_events_due", "status", "next_attempt_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    source: Mapped[ServerEventSource] = mapped_column(
        postgres_enum(ServerEventSource, "server_event_source"), nullable=False
    )
    event_name: Mapped[str] = mapped_column(String(64), nullable=False)
    event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    shopify_market_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pixel_id: Mapped[str] = mapped_column(String(32), nullable=False)
    marketing_consent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[ServerEventStatus] = mapped_column(
        postgres_enum(ServerEventStatus, "server_event_status"), default=ServerEventStatus.RECEIVED, nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    meta_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PendingPurchase(Base):
    """The Purchase join: the relayed browser half and the hashed orders/create
    customer data meet here by order ID. Expires after 7 days."""

    __tablename__ = "pending_purchases"
    __table_args__ = (UniqueConstraint("tenant_id", "order_id", name="uq_pending_purchases_tenant_order"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    browser_half: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    hashed_customer_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
