"""markets: the shop's Markets as last fetched from the Admin API (spec §6).

Revision ID: 007_markets
Revises: 006_multi_pixel_tables
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "007_markets"
down_revision = "006_multi_pixel_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "markets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("shopify_market_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("market_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("regions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("added_after_first_sync", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "shopify_market_id", name="uq_markets_tenant_market"),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("markets")
