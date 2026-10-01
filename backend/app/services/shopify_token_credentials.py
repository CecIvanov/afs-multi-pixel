"""Value object for a Shopify offline token + its refresh chain.

Shopify **expiring offline access tokens** (opted into on the Node side via
``future: { expiringOfflineAccessTokens }``) come with an ``expires_in`` and a
companion ``refresh_token`` that itself expires. This dataclass parses the OAuth
refresh response into absolute expiry timestamps and answers "did anything
actually change?" so a no-op refresh doesn't churn the tenant row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class ShopifyTokenCredentials:
    access_token: str
    scopes: str | None = None
    refresh_token: str | None = None
    access_token_expires_at: datetime | None = None
    refresh_token_expires_at: datetime | None = None

    @classmethod
    def from_oauth_refresh_response(
        cls,
        payload: dict[str, object],
        *,
        now: datetime | None = None,
    ) -> "ShopifyTokenCredentials":
        """Build from Shopify's ``/admin/oauth/access_token`` JSON response.

        Non-expiring (classic) tokens simply omit ``expires_in`` — we leave the
        expiry timestamps NULL, and the discovery sweep never picks them up.
        """
        reference = now or datetime.now(UTC)
        expires_in = int(payload.get("expires_in") or 0)
        refresh_expires_in = int(payload.get("refresh_token_expires_in") or 0)
        scope_value = payload.get("scope")
        scopes = str(scope_value).strip() if scope_value else None
        refresh_token_value = payload.get("refresh_token")
        return cls(
            access_token=str(payload["access_token"]),
            scopes=scopes or None,
            refresh_token=str(refresh_token_value) if refresh_token_value else None,
            access_token_expires_at=(
                reference + timedelta(seconds=expires_in) if expires_in > 0 else None
            ),
            refresh_token_expires_at=(
                reference + timedelta(seconds=refresh_expires_in) if refresh_expires_in > 0 else None
            ),
        )

    def metadata_changed(self, other: "ShopifyTokenCredentials") -> bool:
        return (
            self.access_token != other.access_token
            or (self.scopes or "") != (other.scopes or "")
            or (self.refresh_token or "") != (other.refresh_token or "")
            or self.access_token_expires_at != other.access_token_expires_at
            or self.refresh_token_expires_at != other.refresh_token_expires_at
        )

    @classmethod
    def from_tenant(cls, tenant: object) -> "ShopifyTokenCredentials":
        return cls(
            access_token=str(getattr(tenant, "access_token", "") or ""),
            scopes=getattr(tenant, "scopes", None),
            refresh_token=getattr(tenant, "refresh_token", None),
            access_token_expires_at=getattr(tenant, "access_token_expires_at", None),
            refresh_token_expires_at=getattr(tenant, "refresh_token_expires_at", None),
        )
