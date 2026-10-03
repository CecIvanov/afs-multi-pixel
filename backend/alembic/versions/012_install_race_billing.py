"""tenants.last_authenticated_at (the uninstall job skips a webhook older than the
latest OAuth/app open, so a quick reinstall isn't undone), the "uninstall"
billing event source (an uninstall resets the plan) and the
"subscription_check" job (app_subscriptions/update re-reads the plan).

Revision ID: 012_install_race_billing
Revises: 011_market_pixel_state
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "012_install_race_billing"
down_revision = "011_market_pixel_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("last_authenticated_at", sa.DateTime(timezone=True)))
    # ADD VALUE is transaction-safe on PG 12+ as long as the value isn't used in
    # the same transaction.
    op.execute(sa.text("ALTER TYPE billing_reconcile_source ADD VALUE IF NOT EXISTS 'uninstall'"))
    op.execute(sa.text("ALTER TYPE async_job_operation ADD VALUE IF NOT EXISTS 'subscription_check'"))


def downgrade() -> None:
    # Enum values can't be dropped in Postgres; they stay unused.
    op.drop_column("tenants", "last_authenticated_at")
