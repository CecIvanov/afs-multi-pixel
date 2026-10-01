"""AFS Multi Pixel tables: market_pixels, server_events, pending_purchases; the
orders_create and markets_sync job operations.

Revision ID: 006_multi_pixel_tables
Revises: 005_shopify_token_refresh
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "006_multi_pixel_tables"
down_revision = "005_shopify_token_refresh"
branch_labels = None
depends_on = None

token_state = postgresql.ENUM("ok", "rejected", name="token_state", create_type=False)
server_event_source = postgresql.ENUM("relay", "webhook", name="server_event_source", create_type=False)
server_event_status = postgresql.ENUM(
    "received", "sent", "skipped", "waiting", "rejected", "failed", "paused",
    name="server_event_status", create_type=False,
)


def upgrade() -> None:
    # ADD VALUE is transaction-safe on PG 12+ as long as the value isn't used in
    # the same transaction.
    op.execute(sa.text("ALTER TYPE async_job_operation ADD VALUE IF NOT EXISTS 'orders_create'"))
    op.execute(sa.text("ALTER TYPE async_job_operation ADD VALUE IF NOT EXISTS 'markets_sync'"))

    bind = op.get_bind()
    token_state.create(bind, checkfirst=True)
    server_event_source.create(bind, checkfirst=True)
    server_event_status.create(bind, checkfirst=True)

    op.create_table(
        "market_pixels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("shopify_market_id", sa.BigInteger(), nullable=False),
        sa.Column("pixel_id", sa.String(32), nullable=False),
        sa.Column("pixel_name", sa.String(255)),
        sa.Column("capi_token_encrypted", sa.Text()),
        sa.Column("test_event_code", sa.String(64)),
        sa.Column("token_state", token_state, nullable=False, server_default="ok"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "shopify_market_id", name="uq_market_pixels_tenant_market"),
        if_not_exists=True,
    )

    op.create_table(
        "server_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("source", server_event_source, nullable=False),
        sa.Column("event_name", sa.String(64), nullable=False),
        sa.Column("event_id", sa.String(255), nullable=False),
        sa.Column("shopify_market_id", sa.BigInteger(), nullable=False),
        sa.Column("pixel_id", sa.String(32), nullable=False),
        sa.Column("marketing_consent", sa.Boolean(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), server_default="{}"),
        sa.Column("status", server_event_status, nullable=False, server_default="received"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("meta_response", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        if_not_exists=True,
    )
    op.create_index("ix_server_events_tenant_event_id", "server_events", ["tenant_id", "event_id"], if_not_exists=True)
    op.create_index("ix_server_events_due", "server_events", ["status", "next_attempt_at"], if_not_exists=True)

    op.create_table(
        "pending_purchases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("browser_half", postgresql.JSONB()),
        sa.Column("hashed_customer_data", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "order_id", name="uq_pending_purchases_tenant_order"),
        if_not_exists=True,
    )


def downgrade() -> None:
    # Postgres has no DROP VALUE for an enum; the two async_job_operation labels
    # are left in place (harmless).
    op.drop_table("pending_purchases")
    op.drop_table("server_events")
    op.drop_table("market_pixels")
    server_event_status.drop(op.get_bind(), checkfirst=True)
    server_event_source.drop(op.get_bind(), checkfirst=True)
    token_state.drop(op.get_bind(), checkfirst=True)
