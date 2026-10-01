"""Offline-token refresh: token_refresh job op + tenant token-sweep indexes.

The tenant token columns (refresh_token, access_token_expires_at,
refresh_token_expires_at, shopify_refresh_token_revoked_at) already exist from
001. This migration adds the enum value the durable job uses and two partial
indexes that keep the once-a-minute discovery sweep cheap as the tenant table
grows (it only ever scans active tenants that actually hold a refresh token).

Revision ID: 005_shopify_token_refresh
Revises: 004_billing_engine
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "005_shopify_token_refresh"
down_revision = "004_billing_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # New durable-queue operation. IF NOT EXISTS keeps this idempotent; on PG 12+
    # ADD VALUE is transaction-safe as long as the value isn't used in the same
    # transaction (we only add it + build indexes here).
    op.execute(
        sa.text("ALTER TYPE async_job_operation ADD VALUE IF NOT EXISTS 'token_refresh'")
    )
    # Partial index: the discovery sweep filters WHERE status='active' AND
    # refresh_token IS NOT NULL, ordering by nearest access-token expiry.
    op.create_index(
        "ix_tenants_active_access_token_expires_at",
        "tenants",
        ["access_token_expires_at"],
        unique=False,
        postgresql_where=sa.text("status = 'active' AND refresh_token IS NOT NULL"),
        if_not_exists=True,
    )
    op.create_index(
        "ix_tenants_active_refresh_token_revoked_at",
        "tenants",
        ["shopify_refresh_token_revoked_at"],
        unique=False,
        postgresql_where=sa.text("status = 'active'"),
        if_not_exists=True,
    )


def downgrade() -> None:
    # Postgres has no DROP VALUE for an enum; the 'token_refresh' label is left in
    # place (harmless). Only the indexes are reversible.
    op.drop_index("ix_tenants_active_refresh_token_revoked_at", table_name="tenants", if_exists=True)
    op.drop_index("ix_tenants_active_access_token_expires_at", table_name="tenants", if_exists=True)
