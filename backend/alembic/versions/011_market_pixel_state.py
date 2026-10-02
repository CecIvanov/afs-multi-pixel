"""market_pixels.active (Deactivate keeps the pair) and the last Check with Meta
(result, error, time) for the Market page's connection panel, and
server_events.order_number so the event table finds a Purchase by the order
number the merchant sees (#1001).

Revision ID: 011_market_pixel_state
Revises: 010_subscription_flag
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "011_market_pixel_state"
down_revision = "010_subscription_flag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("market_pixels", sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("market_pixels", sa.Column("last_check_ok", sa.Boolean()))
    op.add_column("market_pixels", sa.Column("last_check_error", sa.Text()))
    op.add_column("market_pixels", sa.Column("last_checked_at", sa.DateTime(timezone=True)))
    op.add_column("server_events", sa.Column("order_number", sa.String(32)))


def downgrade() -> None:
    op.drop_column("server_events", "order_number")
    op.drop_column("market_pixels", "last_checked_at")
    op.drop_column("market_pixels", "last_check_error")
    op.drop_column("market_pixels", "last_check_ok")
    op.drop_column("market_pixels", "active")
