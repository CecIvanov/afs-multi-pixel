"""Webhook events + durable async job queue.

Revision ID: 003_webhook_events_and_jobs
Revises: 002_seed_billing_plans
Create Date: 2026-01-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "003_webhook_events_and_jobs"
down_revision = "002_seed_billing_plans"
branch_labels = None
depends_on = None

webhook_event_status = postgresql.ENUM("received", "processed", "failed", name="webhook_event_status", create_type=False)
async_job_status = postgresql.ENUM("pending", "processing", "completed", "failed", name="async_job_status", create_type=False)
async_job_operation = postgresql.ENUM(
    "app_uninstall", "shop_redact", "customer_data_request", "customer_redact",
    "scopes_update", "shop_info_fetch", "example_op",
    name="async_job_operation", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    webhook_event_status.create(bind, checkfirst=True)
    async_job_status.create(bind, checkfirst=True)
    async_job_operation.create(bind, checkfirst=True)

    op.create_table(
        "webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id")),
        sa.Column("topic", sa.String(100), nullable=False),
        sa.Column("shopify_webhook_id", sa.String(255), nullable=False, unique=True),
        sa.Column("payload", postgresql.JSONB(), server_default="{}"),
        sa.Column("status", webhook_event_status, nullable=False, server_default="received"),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        if_not_exists=True,
    )

    op.create_table(
        "async_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("operation", async_job_operation, nullable=False),
        sa.Column("topic", sa.String(100), nullable=False),
        sa.Column("dedupe_key", sa.String(255), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("shopify_webhook_id", sa.String(255)),
        sa.Column("webhook_event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("webhook_events.id", ondelete="SET NULL")),
        sa.Column("payload", postgresql.JSONB()),
        sa.Column("status", async_job_status, nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("claimed_by", sa.String(255)),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("last_error_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        if_not_exists=True,
    )
    op.create_index(
        "ix_async_jobs_pending_dedupe", "async_jobs",
        ["tenant_id", "operation", "dedupe_key"], unique=True,
        postgresql_where=sa.text("status = 'pending'"), if_not_exists=True,
    )
    op.create_index("ix_async_jobs_claim", "async_jobs", ["status", "priority", "created_at"], if_not_exists=True)
    op.create_index("ix_async_jobs_retention", "async_jobs", ["status", "finished_at"], if_not_exists=True)


def downgrade() -> None:
    op.drop_table("async_jobs")
    op.drop_table("webhook_events")
    async_job_operation.drop(op.get_bind(), checkfirst=True)
    async_job_status.drop(op.get_bind(), checkfirst=True)
    webhook_event_status.drop(op.get_bind(), checkfirst=True)
