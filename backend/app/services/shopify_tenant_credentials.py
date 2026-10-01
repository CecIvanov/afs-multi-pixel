"""Small predicates about a tenant's Shopify credential state.

Kept in one place so the workers, the shop-info fetch, and any Admin-API job you
add all agree on "can this tenant call Shopify right now?" — which, once expiring
offline tokens are in play, also means "is its refresh chain still alive?".
"""

from __future__ import annotations

from app.models import AsyncJobOperation, Tenant, TenantStatus

# Jobs allowed to run even while the offline refresh chain is dead. These either
# don't call the Shopify Admin API (local DB work) or must still fire so the app
# winds down cleanly. Everything else is pointless without a live token.
JOBS_ALLOWED_WHEN_REFRESH_REVOKED: frozenset[AsyncJobOperation] = frozenset(
    {
        AsyncJobOperation.APP_UNINSTALL,
        AsyncJobOperation.SHOP_REDACT,
        AsyncJobOperation.CUSTOMER_DATA_REQUEST,
        AsyncJobOperation.CUSTOMER_REDACT,
        AsyncJobOperation.SCOPES_UPDATE,
    }
)


def is_tenant_refresh_token_revoked(tenant: Tenant) -> bool:
    return tenant.shopify_refresh_token_revoked_at is not None


def tenant_can_call_admin_api(tenant: Tenant) -> bool:
    return (
        bool(str(tenant.access_token or "").strip())
        and tenant.status == TenantStatus.ACTIVE
        and not is_tenant_refresh_token_revoked(tenant)
    )


def is_admin_job_blocked_when_refresh_revoked(
    tenant: Tenant,
    operation: AsyncJobOperation,
) -> bool:
    if not is_tenant_refresh_token_revoked(tenant):
        return False
    return operation not in JOBS_ALLOWED_WHEN_REFRESH_REVOKED
