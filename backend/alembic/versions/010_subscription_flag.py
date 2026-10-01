"""tenants.subscription_active (NULL until first checked) and the
subscription_update job operation.

Revision ID: 010_subscription_flag
Revises: 009_server_event_log
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "010_subscription_flag"
down_revision = "009_server_event_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TYPE async_job_operation ADD VALUE IF NOT EXISTS 'subscription_update'"))
    op.add_column("tenants", sa.Column("subscription_active", sa.Boolean()))


def downgrade() -> None:
    op.drop_column("tenants", "subscription_active")
