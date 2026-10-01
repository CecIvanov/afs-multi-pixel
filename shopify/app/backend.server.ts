import { logError } from "./logger.server";
import { getRequestId, getRequestTenantId } from "./request-context.server";
import {
  BackendRequestError,
  isBackendTenantNotFoundError,
  parseBackendErrorDetail,
  shouldLogBackendRequestFailure,
} from "./backend-fetch.helpers.mjs";
import { isIdempotentWebhookTopic } from "./webhook-ingest.shared.mjs";

const backendUrl = process.env.BACKEND_INTERNAL_URL || "http://api:8000";
const internalApiKey = process.env.INTERNAL_API_KEY || "";

type BackendRequestInit = Omit<RequestInit, "headers"> & {
  headers?: Record<string, string>;
  shopDomain?: string;
  tenantId?: string;
};

function backendRequestHeaders(init: BackendRequestInit): Record<string, string> {
  const { shopDomain, headers, tenantId } = init;
  const resolvedTenantId = tenantId || getRequestTenantId();
  return {
    "Content-Type": "application/json",
    "X-Internal-Key": internalApiKey,
    ...(shopDomain ? { "X-Shop-Domain": shopDomain } : {}),
    ...(resolvedTenantId ? { "X-Tenant-Id": resolvedTenantId } : {}),
    ...(getRequestId() ? { "X-Request-Id": getRequestId() } : {}),
    ...headers,
  };
}

async function backendFetch<T>(path: string, init: BackendRequestInit = {}): Promise<T> {
  const { shopDomain, ...requestInit } = init;
  const response = await fetch(`${backendUrl}${path}`, {
    ...requestInit,
    headers: backendRequestHeaders(init),
  });

  if (!response.ok) {
    const text = await response.text();
    const detail = parseBackendErrorDetail(text);
    if (shouldLogBackendRequestFailure(response.status, detail)) {
      logError("backend_request_failed", new Error(detail), { path, status: response.status, shop: shopDomain });
    }
    throw new BackendRequestError(response.status, detail, {
      code: response.status === 404 ? "TENANT_NOT_FOUND" : undefined,
    });
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export type TenantRecord = {
  id: string;
  shop_domain: string;
  status: string;
  created_at: string;
  installed_at: string | null;
  app_ui_locale: string;
  plan_handle: string | null;
  feature_flags: Record<string, boolean>;
};

type InstallPayload = {
  shop_domain: string;
  access_token: string;
  scopes?: string;
  refresh_token?: string;
  access_token_expires_at?: string;
  refresh_token_expires_at?: string;
};

export async function syncShopInstall(payload: InstallPayload): Promise<TenantRecord> {
  return backendFetch<TenantRecord>("/api/v1/internal/shopify/install", {
    method: "POST",
    shopDomain: payload.shop_domain,
    body: JSON.stringify(payload),
  });
}

export async function syncShopSession(payload: InstallPayload): Promise<TenantRecord> {
  return backendFetch<TenantRecord>("/api/v1/internal/shopify/session-sync", {
    method: "POST",
    shopDomain: payload.shop_domain,
    body: JSON.stringify(payload),
  });
}

/**
 * Forward a verified webhook to the backend, which records it (dedup) and enqueues
 * a durable job. For lifecycle/compliance topics a "tenant not found" is swallowed
 * (the shop is gone / not yet provisioned) so the route can still return 2xx.
 */
export async function ingestShopifyWebhook(params: {
  shop: string;
  topic: string;
  webhookId?: string | null;
  payload?: Record<string, unknown>;
  webhookContext?: Record<string, unknown>;
}) {
  const body = {
    shop_domain: params.shop,
    topic: params.topic,
    shopify_webhook_id: params.webhookId ?? null,
    payload: params.payload ?? null,
    webhook_context: params.webhookContext ?? null,
  };
  try {
    return await backendFetch<{
      status: string;
      duplicate: boolean;
      job_id: string | null;
      webhook_event_id: string | null;
    }>("/api/v1/internal/shopify/webhooks/ingest", {
      method: "POST",
      shopDomain: params.shop,
      body: JSON.stringify(body),
    });
  } catch (error) {
    if (isIdempotentWebhookTopic(params.topic) && isBackendTenantNotFoundError(error)) {
      return { status: "ignored", duplicate: false, job_id: null, webhook_event_id: null };
    }
    throw error;
  }
}

export async function getTenantByShop(shopDomain: string): Promise<TenantRecord> {
  return backendFetch<TenantRecord>(
    `/api/v1/internal/tenants/by-shop/${encodeURIComponent(shopDomain)}`,
    { shopDomain },
  );
}

export type BillingRecord = {
  plan_handle: string;
  plan_name: string;
  pending_plan_handle: string | null;
  status: string;
  used: number;
  quota: number | null;
  supports: Record<string, boolean>;
};

export async function fetchBillingByShop(shopDomain: string): Promise<BillingRecord> {
  return backendFetch<BillingRecord>(
    `/api/v1/internal/tenants/by-shop/${encodeURIComponent(shopDomain)}/billing`,
    { shopDomain },
  );
}

export async function reconcileBilling(payload: {
  shop_domain: string;
  source: string;
  partner_snapshot: Record<string, unknown>;
}) {
  return backendFetch<{
    status: string;
    action: string;
    effective_plan_handle: string;
    pending_plan_handle: string | null;
  }>("/api/v1/internal/billing/reconcile", {
    method: "POST",
    shopDomain: payload.shop_domain,
    body: JSON.stringify(payload),
  });
}

// --- Markets and the Pixel Mapping (the Market health page) ----------------------
export type MarketPixelRecord = {
  pixel_id: string;
  pixel_name: string | null;
  test_event_code: string | null;
  token_state: "ok" | "rejected";
  has_token: boolean;
  token_error: string | null;
};

export type MarketStatsRecord = {
  browser: number;
  server: number;
  purchases: number;
  series: number[];
  last_event_at: string | null;
};

export type MarketRecord = {
  shopify_market_id: number;
  name: string;
  market_type: string;
  status: string;
  regions: string[];
  first_seen_at: string;
  is_new: boolean;
  pixel: MarketPixelRecord | null;
  stats: MarketStatsRecord;
};

export type PixelCheckRecord = {
  ok: boolean;
  pixel_name: string | null;
  owner_name: string | null;
  error: string | null;
};

export type PixelInput = { pixel_id: string; token?: string; test_event_code?: string };

function marketsPath(shopDomain: string, suffix = "") {
  return `/api/v1/internal/tenants/by-shop/${encodeURIComponent(shopDomain)}/markets${suffix}`;
}

/** The shop's Markets; `sync` re-fetches them from Shopify first (app open). */
export async function listMarkets(shopDomain: string, { sync = false } = {}) {
  return backendFetch<{
    markets: MarketRecord[];
    summary: { browser_24h: number; server_24h: number };
    setup: SetupRecord;
    sync_error: string | null;
  }>(
    marketsPath(shopDomain, sync ? "?sync=true" : ""),
    { shopDomain },
  );
}

export async function checkMarketPixel(shopDomain: string, marketId: number, input: PixelInput) {
  return backendFetch<PixelCheckRecord>(marketsPath(shopDomain, `/${marketId}/pixel/check`), {
    method: "POST",
    shopDomain,
    body: JSON.stringify(input),
  });
}

/** Saves only a pair that passes Check with Meta; a refusal is a 422 with the reason. */
export async function saveMarketPixel(shopDomain: string, marketId: number, input: PixelInput) {
  return backendFetch<MarketRecord>(marketsPath(shopDomain, `/${marketId}/pixel`), {
    method: "PUT",
    shopDomain,
    body: JSON.stringify(input),
  });
}

export async function removeMarketPixel(shopDomain: string, marketId: number) {
  return backendFetch<MarketRecord>(marketsPath(shopDomain, `/${marketId}/pixel`), {
    method: "DELETE",
    shopDomain,
  });
}

/** Hand a Relay to the backend, which decrypts, validates and stores it. */
export async function forwardRelay(relay: {
  body: string;
  origin: string | null;
  ip: string | null;
  user_agent: string | null;
}) {
  return backendFetch<{ outcome: string }>("/api/v1/internal/relay", {
    method: "POST",
    body: JSON.stringify(relay),
  });
}

export type EventLogRecord = {
  created_at: string;
  event_name: string;
  event_id: string;
  shopify_market_id: number;
  sent_as: string;
  status: string;
  detail: string | null;
};

export async function listEvents(shopDomain: string, marketId?: number) {
  const query = marketId ? `?market_id=${marketId}` : "";
  return backendFetch<{ events: EventLogRecord[] }>(
    `/api/v1/internal/tenants/by-shop/${encodeURIComponent(shopDomain)}/events${query}`,
    { shopDomain },
  );
}

export type SetupRecord = { consent_confirmed: boolean; verified_in_meta: boolean };

export async function updateSetup(shopDomain: string, changes: Partial<SetupRecord>) {
  return backendFetch<SetupRecord>(`/api/v1/internal/tenants/by-shop/${encodeURIComponent(shopDomain)}/setup`, {
    method: "POST",
    shopDomain,
    body: JSON.stringify(changes),
  });
}

export async function reportSubscription(shopDomain: string, active: boolean) {
  return backendFetch<SetupRecord>(
    `/api/v1/internal/tenants/by-shop/${encodeURIComponent(shopDomain)}/subscription`,
    { method: "POST", shopDomain, body: JSON.stringify({ active }) },
  );
}
