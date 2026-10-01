"""app_keys (the Relay key pair) and the shop's storefront allowlist and setup
flags on tenants; the pixel_mapping_publish and storefront_hosts_sync operations.

Revision ID: 008_relay_key_and_storefront
Revises: 007_markets
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "008_relay_key_and_storefront"
down_revision = "007_markets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TYPE async_job_operation ADD VALUE IF NOT EXISTS 'pixel_mapping_publish'"))
    op.execute(sa.text("ALTER TYPE async_job_operation ADD VALUE IF NOT EXISTS 'storefront_hosts_sync'"))

    op.create_table(
        "app_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("private_key_encrypted", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        if_not_exists=True,
    )
    op.add_column("tenants", sa.Column("storefront_hosts", postgresql.JSONB(), nullable=False, server_default="[]"))
    op.add_column("tenants", sa.Column("storefront_hosts_synced_at", sa.DateTime(timezone=True)))
    op.add_column("tenants", sa.Column("consent_confirmed_at", sa.DateTime(timezone=True)))
    op.add_column("tenants", sa.Column("verified_in_meta_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("tenants", "verified_in_meta_at")
    op.drop_column("tenants", "consent_confirmed_at")
    op.drop_column("tenants", "storefront_hosts_synced_at")
    op.drop_column("tenants", "storefront_hosts")
    op.drop_table("app_keys")
