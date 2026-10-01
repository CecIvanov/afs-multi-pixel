"""market_pixels.token_error (Meta's answer when it rejects a token, shown on the
Market's tile) and a time index for the event log and the 24 h counts.

Revision ID: 009_server_event_log
Revises: 008_relay_key_and_storefront
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "009_server_event_log"
down_revision = "008_relay_key_and_storefront"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("market_pixels", sa.Column("token_error", sa.Text()))
    op.create_index(
        "ix_server_events_tenant_created", "server_events", ["tenant_id", "created_at"], if_not_exists=True
    )


def downgrade() -> None:
    op.drop_index("ix_server_events_tenant_created", "server_events")
    op.drop_column("market_pixels", "token_error")
