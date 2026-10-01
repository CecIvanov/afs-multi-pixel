"""Seed the default billing plans (free, pro).

Idempotent upsert so it can run on every deploy. These mirror app.config.json's
`billing.plans`; if you change plans there, update this seed (or re-run
scripts/db/seed.sh, which is config-driven). Phase 3 unifies the two sources.

Revision ID: 002_seed_billing_plans
Revises: 001_initial_schema
Create Date: 2026-01-01
"""

from __future__ import annotations

from alembic import op

revision = "002_seed_billing_plans"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO billing_plans (handle, name, monthly_label_limit, shopify_plan_name)
        VALUES
          ('free', 'Free', 50, NULL),
          ('pro', 'Pro', NULL, 'Pro')
        ON CONFLICT (handle) DO UPDATE SET
          name = EXCLUDED.name,
          monthly_label_limit = EXCLUDED.monthly_label_limit,
          shopify_plan_name = EXCLUDED.shopify_plan_name
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM billing_plans WHERE handle IN ('free', 'pro')")
