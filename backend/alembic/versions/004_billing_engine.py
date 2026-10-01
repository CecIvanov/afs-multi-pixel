"""Billing engine: pending plan + trial on subscriptions, usage counters, audit.

Revision ID: 004_billing_engine
Revises: 003_webhook_events_and_jobs
Create Date: 2026-01-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "004_billing_engine"
down_revision = "003_webhook_events_and_jobs"
branch_labels = None
depends_on = None

event_type = postgresql.ENUM(
    "initial_selection", "upgrade", "downgrade_scheduled", "downgrade_effective",
    "cancel_scheduled", "cancelled_to_free", "subscription_renewed",
    name="billing_subscription_event_type", create_type=False,
)
reconcile_source = postgresql.ENUM(
    "redirect", "app_load", "billing_page", "scheduled_worker",
    name="billing_reconcile_source", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()

    # Generic quota name (was the delivery-domain "monthly_label_limit").
    op.alter_column("billing_plans", "monthly_label_limit", new_column_name="monthly_quota")

    op.add_column("tenant_subscriptions", sa.Column("pending_billing_plan_id", sa.Integer()))
    op.create_foreign_key(
        "fk_tenant_subscriptions_pending_plan", "tenant_subscriptions", "billing_plans",
        ["pending_billing_plan_id"], ["id"],
    )
    op.add_column("tenant_subscriptions", sa.Column("trial_ends_at", sa.DateTime(timezone=True)))

    op.create_table(
        "usage_counters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quota", sa.Integer(), nullable=False),
        sa.UniqueConstraint("tenant_id", "period_start", name="uq_usage_tenant_period"),
        if_not_exists=True,
    )

    event_type.create(bind, checkfirst=True)
    reconcile_source.create(bind, checkfirst=True)
    op.create_table(
        "billing_subscription_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("event_type", event_type, nullable=False),
        sa.Column("from_plan_handle", sa.String(64)),
        sa.Column("to_plan_handle", sa.String(64)),
        sa.Column("effective_plan_handle", sa.String(64), nullable=False),
        sa.Column("pending_plan_handle", sa.String(64)),
        sa.Column("source", reconcile_source, nullable=False),
        sa.Column("partner_snapshot", postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("billing_subscription_events")
    op.drop_table("usage_counters")
    op.drop_column("tenant_subscriptions", "trial_ends_at")
    op.drop_constraint("fk_tenant_subscriptions_pending_plan", "tenant_subscriptions", type_="foreignkey")
    op.drop_column("tenant_subscriptions", "pending_billing_plan_id")
    op.alter_column("billing_plans", "monthly_quota", new_column_name="monthly_label_limit")
    event_type.drop(op.get_bind(), checkfirst=True)
    reconcile_source.drop(op.get_bind(), checkfirst=True)
