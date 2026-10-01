"""Keep every active tenant's Shopify **offline** token alive — no matter what.

Public App-Store apps use *expiring* offline access tokens (enabled on the Node
side via ``future: { expiringOfflineAccessTokens }``). The token expires; a
companion refresh token mints the next one via
``POST https://{shop}/admin/oauth/access_token`` with ``grant_type=refresh_token``.

Background workers call the Admin API long after the merchant last opened the app
(order syncs, scheduled jobs, webhooks). If nothing refreshes the offline token,
it silently expires and *every* background call 401s — the app is effectively
dead for that store with no visible error. This service prevents that two ways:

1. **Proactive** — ``discover_and_enqueue_refreshes`` runs on a 1-minute beat,
   finds tenants whose access token (or whole refresh chain) is nearing expiry,
   and enqueues a durable ``token_refresh`` job that does the exchange. The token
   is renewed *before* it can lapse.
2. **Reactive** — the job queue calls ``refresh_tenant_tokens(force=True)`` when
   any Admin-API job 401s, then retries once (see AsyncJobService).

A refresh token Shopify definitively rejects marks the tenant revoked (the
merchant must re-auth); transient failures just retry via the job's backoff.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.logging_config import get_logger
from app.models import Tenant, TenantStatus
from app.services.shopify_oauth_refresh_errors import (
    is_definitive_dead_refresh_token_error,
    parse_oauth_token_error,
)
from app.services.shopify_session_service import ShopifySessionService
from app.services.shopify_tenant_credentials import is_tenant_refresh_token_revoked
from app.services.shopify_token_credentials import ShopifyTokenCredentials
from app.services.tenant_service import TenantService

logger = get_logger().child({"component": "shopify_token_refresh"})


class ShopifyTokenRefreshError(RuntimeError):
    pass


class ShopifyRefreshTokenRevokedError(ShopifyTokenRefreshError):
    """Stored offline refresh token is dead on Shopify's side; merchant must re-auth."""


class ShopifyTokenRefreshService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- proactive discovery -------------------------------------------------
    def discover_and_enqueue_refreshes(self) -> dict[str, int]:
        """Find active tenants due for a refresh and enqueue one durable job each.

        "Due" = the access token expires within ``shopify_token_refresh_lead_minutes``
        OR the refresh chain expires within ``shopify_refresh_token_renew_lead_days``.
        Skips revoked tenants and any tenant that already has a token_refresh job
        pending/processing (the queue's dedupe index is a second guard)."""
        from app.services.async_job_service import AsyncJobService

        settings = get_settings()
        now = datetime.now(UTC)
        access_cutoff = now + timedelta(minutes=settings.shopify_token_refresh_lead_minutes)
        refresh_cutoff = now + timedelta(days=settings.shopify_refresh_token_renew_lead_days)

        tenant_ids = (
            self.db.execute(
                text(
                    """
                    SELECT t.id
                    FROM tenants t
                    WHERE t.status = 'active'
                      AND t.refresh_token IS NOT NULL
                      AND t.shopify_refresh_token_revoked_at IS NULL
                      AND (
                        (t.access_token_expires_at IS NOT NULL AND t.access_token_expires_at <= :access_cutoff)
                        OR (t.refresh_token_expires_at IS NOT NULL AND t.refresh_token_expires_at <= :refresh_cutoff)
                      )
                      AND NOT EXISTS (
                        SELECT 1 FROM async_jobs j
                        WHERE j.tenant_id = t.id
                          AND j.operation = 'token_refresh'
                          AND j.status IN ('pending', 'processing')
                      )
                    """
                ),
                {"access_cutoff": access_cutoff, "refresh_cutoff": refresh_cutoff},
            )
            .scalars()
            .all()
        )

        job_service = AsyncJobService(self.db)
        enqueued = 0
        for tenant_id in tenant_ids:
            job_service.enqueue_token_refresh(tenant_id, topic="scheduled/token_refresh")
            enqueued += 1

        payload = {"candidates": len(tenant_ids), "enqueued": enqueued}
        if enqueued:
            logger.info("shopify_token_refresh.discovery_enqueued", payload)
        return payload

    # --- the refresh itself --------------------------------------------------
    def refresh_tenant_tokens(self, tenant: Tenant, *, reason: str, force: bool = False) -> bool:
        """Exchange the refresh token for a fresh offline access token.

        Returns True when the token was refreshed, False when nothing was due /
        possible. ``force`` skips the not-due short-circuit (used by 401 recovery).
        Raises ShopifyRefreshTokenRevokedError when Shopify rejects the refresh
        token — the tenant is flagged revoked first so callers stop retrying."""
        if tenant.status != TenantStatus.ACTIVE:
            return False

        if is_tenant_refresh_token_revoked(tenant):
            logger.info(
                "shopify_token_refresh.skipped_revoked",
                {"tenantId": str(tenant.id), "shop": tenant.shop_domain, "reason": reason},
            )
            return False

        credentials = self._resolve_refresh_source(tenant)
        if credentials is None or not credentials.refresh_token:
            # No refresh token anywhere = a classic (non-expiring) token; nothing to do.
            logger.info(
                "shopify_token_refresh.skipped_non_expiring",
                {"tenantId": str(tenant.id), "shop": tenant.shop_domain, "reason": reason},
            )
            return False

        settings = get_settings()
        now = datetime.now(UTC)
        if not force and credentials.access_token_expires_at is not None:
            access_ok = credentials.access_token_expires_at > (
                now + timedelta(minutes=settings.shopify_token_refresh_lead_minutes)
            )
            chain_ok = (
                credentials.refresh_token_expires_at is None
                or credentials.refresh_token_expires_at
                > now + timedelta(days=settings.shopify_refresh_token_renew_lead_days)
            )
            if access_ok and chain_ok:
                return False

        try:
            refreshed = self._exchange_refresh_token(tenant.shop_domain, credentials.refresh_token)
        except ShopifyRefreshTokenRevokedError as exc:
            TenantService(self.db).mark_refresh_token_revoked(tenant, reason=reason, detail=str(exc))
            raise

        TenantService(self.db).apply_shopify_credentials(tenant, refreshed, reason=f"token_refresh:{reason}")
        logger.info(
            "shopify_token_refresh.completed",
            {
                "tenantId": str(tenant.id),
                "shop": tenant.shop_domain,
                "reason": reason,
                "accessTokenExpiresAt": (
                    refreshed.access_token_expires_at.isoformat()
                    if refreshed.access_token_expires_at
                    else None
                ),
            },
        )
        return True

    def _resolve_refresh_source(self, tenant: Tenant) -> ShopifyTokenCredentials | None:
        """Prefer the tenant row; fall back to the Prisma Session (self-heal a
        tenant installed before this column existed, backfilling it on the way)."""
        current = ShopifyTokenCredentials.from_tenant(tenant)
        if current.refresh_token:
            return current

        session_row = ShopifySessionService(self.db).get_offline_session(tenant.shop_domain)
        if not session_row:
            return None
        session_credentials = ShopifySessionService.credentials_from_session_row(session_row)
        if session_credentials is None or not session_credentials.refresh_token:
            return None

        TenantService(self.db).apply_shopify_credentials(
            tenant, session_credentials, reason="session_backfill"
        )
        return session_credentials

    def _exchange_refresh_token(self, shop_domain: str, refresh_token: str) -> ShopifyTokenCredentials:
        settings = get_settings()
        if not settings.shopify_api_key or not settings.shopify_api_secret:
            raise ShopifyTokenRefreshError(
                "Shopify app credentials are not configured (set SHOPIFY_API_KEY / "
                "SHOPIFY_API_SECRET on the backend services)"
            )

        url = f"https://{shop_domain.strip().lower()}/admin/oauth/access_token"
        try:
            response = httpx.post(
                url,
                data={
                    "client_id": settings.shopify_api_key,
                    "client_secret": settings.shopify_api_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            raise ShopifyTokenRefreshError(f"Shopify token refresh request failed: {exc}") from exc

        if response.status_code >= 400:
            body = response.text
            oauth_error = parse_oauth_token_error(body)
            if is_definitive_dead_refresh_token_error(oauth_error):
                raise ShopifyRefreshTokenRevokedError(
                    f"Shopify refresh token rejected for '{shop_domain}': {body}"
                )
            raise ShopifyTokenRefreshError(f"Shopify token refresh HTTP {response.status_code}: {body}")

        payload = response.json()
        if not isinstance(payload, dict) or not payload.get("access_token"):
            raise ShopifyTokenRefreshError(
                f"Shopify token refresh returned an unexpected payload for '{shop_domain}'"
            )
        return ShopifyTokenCredentials.from_oauth_refresh_response(payload)


def refresh_tenant_tokens_by_id(db: Session, tenant_id: uuid.UUID, *, reason: str, force: bool = False) -> bool:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        return False
    return ShopifyTokenRefreshService(db).refresh_tenant_tokens(tenant, reason=reason, force=force)
