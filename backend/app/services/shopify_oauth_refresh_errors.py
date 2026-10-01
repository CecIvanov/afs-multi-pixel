"""Classify Shopify OAuth token-endpoint errors.

Refreshing an offline token can fail two very different ways:

- **Transient** — network blip, 5xx, rate limit. Retry; the token is fine.
- **Definitively dead** — Shopify rejects the *stored refresh token* itself
  (revoked, superseded, app reinstalled). No retry will help; the merchant has
  to re-auth. We flag the tenant so background work stops hammering a dead chain.

Getting this wrong in either direction is costly: revoke on a blip and you force
a needless re-auth; treat a dead token as transient and you retry forever. The
matching below is deliberately narrow — only Shopify's explicit refresh-token
rejections count as definitive.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class OAuthTokenError:
    error: str | None
    error_description: str | None


def parse_oauth_token_error(body: str) -> OAuthTokenError | None:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    error = str(payload.get("error") or "").strip() or None
    description = str(payload.get("error_description") or "").strip() or None
    if not error and not description:
        return None
    return OAuthTokenError(error=error, error_description=description)


def is_definitive_dead_refresh_token_error(oauth_error: OAuthTokenError | None) -> bool:
    """True only when Shopify rejects the stored refresh token (not transient failures)."""
    if oauth_error is None:
        return False

    description = (oauth_error.error_description or "").lower()

    if oauth_error.error == "invalid_request":
        return "active refresh_token" in description

    if oauth_error.error == "invalid_grant":
        return "refresh_token" in description or "refresh token" in description

    return False


def is_shopify_auth_error(message: str) -> bool:
    """Heuristic: did an Admin API call fail because the access token is invalid?

    Used by the job queue's reactive recovery — a 401/403 from Shopify means the
    stored offline token has expired or rotated, so a forced refresh + retry may
    rescue the job. Kept intentionally loose since adapters wrap errors as strings.
    """
    lowered = (message or "").lower()
    return (
        "401" in lowered
        or "403" in lowered
        or "unauthorized" in lowered
        or "invalid api key or access token" in lowered
        or "invalid_token" in lowered
    )
