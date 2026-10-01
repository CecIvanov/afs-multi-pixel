import {
  getTenantByShop,
  syncShopInstall,
  syncShopSession,
  type TenantRecord,
} from "./backend.server";
import { isBackendTenantNotFoundError } from "./backend-fetch.helpers.mjs";
import { logError, logInfo } from "./logger.server";
import { setRequestTenantId } from "./request-context.server";

type SessionLike = {
  shop: string;
  accessToken?: string | null;
  scope?: string | null;
  expires?: Date | null;
  refreshToken?: string | null;
  refreshTokenExpires?: Date | null;
};

// Dedup concurrent syncs for the same shop (multiple tabs / rapid navigation)
// so we never race a duplicate-insert on the tenants row.
const inFlight = new Map<string, Promise<TenantRecord>>();

export async function ensureBackendTenant(session: SessionLike): Promise<TenantRecord> {
  const existing = inFlight.get(session.shop);
  if (existing) return existing;
  const promise = syncBackendTenant(session).finally(() => inFlight.delete(session.shop));
  inFlight.set(session.shop, promise);
  return promise;
}

function iso(value: Date | null | undefined): string | undefined {
  return value ? value.toISOString() : undefined;
}

function credentialsPayload(session: SessionLike) {
  return {
    shop_domain: session.shop,
    access_token: session.accessToken as string,
    scopes: session.scope || undefined,
    refresh_token: session.refreshToken || undefined,
    access_token_expires_at: iso(session.expires),
    refresh_token_expires_at: iso(session.refreshTokenExpires),
  };
}

async function syncBackendTenant(session: SessionLike): Promise<TenantRecord> {
  if (!session.accessToken) throw new Error("Missing Shopify session access token");

  let existing: TenantRecord | null = null;
  try {
    existing = await getTenantByShop(session.shop);
    setRequestTenantId(existing.id);
  } catch (error) {
    if (!isBackendTenantNotFoundError(error)) {
      logError("tenant_sync_probe_failed", error, { shop: session.shop });
    }
  }

  const reason = !existing ? "create" : existing.status !== "active" ? "reactivate" : "refresh";
  logInfo("tenant_sync", { shop: session.shop, reason });

  const payload = credentialsPayload(session);
  const tenant = reason === "refresh" ? await syncShopSession(payload) : await syncShopInstall(payload);
  setRequestTenantId(tenant.id);
  return tenant;
}
