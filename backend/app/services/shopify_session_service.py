"""Read/write the Prisma-owned Shopify OAuth ``Session`` table from Python.

Prisma (the Node side) owns this table, but the backend touches it for exactly
one reason: **token-refresh write-back**. When the backend refreshes a tenant's
offline token, the new access + refresh token must also land in the ``Session``
row, because Shopify offline refresh tokens are *single-use and rotate* — the old
one is invalidated the instant we exchange it. If we updated only the ``tenants``
row and left Prisma holding the consumed refresh token, the Shopify Node library
would try to refresh with a dead token on the next admin visit and force the
merchant to re-auth. Keeping both copies in lockstep prevents that.

``get_offline_session`` also lets the refresh service backfill a tenant whose
``refresh_token`` column is empty (e.g. installed before this feature existed)
from the session Prisma already captured.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.shopify_token_credentials import ShopifyTokenCredentials


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ShopifySessionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_offline_session(self, shop_domain: str) -> dict[str, Any] | None:
        row = self.db.execute(
            text(
                """
                SELECT
                    id,
                    "accessToken" AS access_token,
                    "refreshToken" AS refresh_token,
                    expires AS access_token_expires_at,
                    "refreshTokenExpires" AS refresh_token_expires_at,
                    scope AS scopes
                FROM "Session"
                WHERE shop = :shop
                  AND "isOnline" = false
                ORDER BY id
                LIMIT 1
                """
            ),
            {"shop": shop_domain},
        ).mappings().first()
        return dict(row) if row else None

    def sync_offline_session_tokens(
        self,
        shop_domain: str,
        credentials: ShopifyTokenCredentials,
    ) -> None:
        """Mirror freshly-refreshed credentials back into the Prisma ``Session`` row
        so the Node library and the backend never diverge on the rotating token.

        No-op when no offline session exists yet (the tenant row is still the
        source of truth for the workers). Prisma stores naive timestamps, so the
        tz-aware expiries are stripped to UTC-naive here.
        """
        session_row = self.get_offline_session(shop_domain)
        if not session_row:
            return

        access_expires = credentials.access_token_expires_at
        refresh_expires = credentials.refresh_token_expires_at
        self.db.execute(
            text(
                """
                UPDATE "Session"
                SET
                    "accessToken" = :access_token,
                    "refreshToken" = :refresh_token,
                    expires = :access_token_expires_at,
                    "refreshTokenExpires" = :refresh_token_expires_at,
                    scope = COALESCE(:scopes, scope)
                WHERE id = :session_id
                """
            ),
            {
                "session_id": session_row["id"],
                "access_token": credentials.access_token,
                "refresh_token": credentials.refresh_token,
                "access_token_expires_at": (
                    access_expires.replace(tzinfo=None) if access_expires else None
                ),
                "refresh_token_expires_at": (
                    refresh_expires.replace(tzinfo=None) if refresh_expires else None
                ),
                "scopes": credentials.scopes,
            },
        )

    @staticmethod
    def credentials_from_session_row(row: dict[str, Any]) -> ShopifyTokenCredentials | None:
        access_token = str(row.get("access_token") or "").strip()
        if not access_token:
            return None
        scopes_value = row.get("scopes")
        refresh_value = row.get("refresh_token")
        return ShopifyTokenCredentials(
            access_token=access_token,
            scopes=str(scopes_value).strip() if scopes_value else None,
            refresh_token=str(refresh_value).strip() if refresh_value else None,
            access_token_expires_at=_as_utc(row.get("access_token_expires_at")),
            refresh_token_expires_at=_as_utc(row.get("refresh_token_expires_at")),
        )
