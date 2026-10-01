"""Initial schema: tenants, tenants_metadata, billing_plans, tenant_subscriptions.

Written idempotently (create type/table checkfirst) because this database is
shared with Prisma's own migration history (which owns only the Session table).

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-01-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

tenant_status = postgresql.ENUM(
    "active", "uninstalled", "suspended", name="tenant_status", create_type=False
)
subscription_status = postgresql.ENUM(
    "active", "cancelled", "frozen", "pending", name="subscription_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    tenant_status.create(bind, checkfirst=True)
    subscription_status.create(bind, checkfirst=True)

    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_domain", sa.String(255), nullable=False, unique=True),
        sa.Column("shopify_shop_id", sa.BigInteger(), unique=True),
        sa.Column("access_token", sa.Text()),
        sa.Column("refresh_token", sa.Text()),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True)),
        sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True)),
        sa.Column("shopify_refresh_token_revoked_at", sa.DateTime(timezone=True)),
        sa.Column("scopes", sa.Text()),
        sa.Column("status", tenant_status, nullable=False, server_default="active"),
        sa.Column("installed_at", sa.DateTime(timezone=True)),
        sa.Column("uninstalled_at", sa.DateTime(timezone=True)),
        sa.Column("app_ui_locale", sa.String(8), nullable=False, server_default="en"),
        sa.Column("feature_flags", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        if_not_exists=True,
    )

    op.create_table(
        "tenants_metadata",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("m_key", sa.String(255), nullable=False),
        sa.Column("m_value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "m_key", name="uq_tenant_metadata_key"),
        if_not_exists=True,
    )

    op.create_table(
        "billing_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("handle", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("monthly_label_limit", sa.Integer()),
        sa.Column("shopify_plan_name", sa.String(100)),
        if_not_exists=True,
    )

    op.create_table(
        "tenant_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("billing_plan_id", sa.Integer(), sa.ForeignKey("billing_plans.id"), nullable=False),
        sa.Column("shopify_subscription_id", sa.String(255)),
        sa.Column("status", subscription_status, nullable=False, server_default="active"),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("tenant_subscriptions")
    op.drop_table("billing_plans")
    op.drop_table("tenants_metadata")
    op.drop_table("tenants")
    subscription_status.drop(op.get_bind(), checkfirst=True)
    tenant_status.drop(op.get_bind(), checkfirst=True)
