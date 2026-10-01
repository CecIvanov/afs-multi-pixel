import { AsyncLocalStorage } from "node:async_hooks";
import { randomUUID } from "node:crypto";
import type { MiddlewareFunction } from "react-router";
import { isRedirectResponse } from "./backend-fetch.helpers.mjs";
import { logUiRequestFailed, logUiRequestFinished, logUiRequestReceived } from "./request-logging.server.ts";

type RequestStore = { requestId: string; shop?: string; tenantId?: string };

const requestStore = new AsyncLocalStorage<RequestStore>();

export function runWithRequestContext<T>(store: RequestStore, fn: () => T): T {
  return requestStore.run(store, fn);
}
export function getRequestId(): string {
  return requestStore.getStore()?.requestId ?? "";
}
export function getRequestShop(): string | undefined {
  return requestStore.getStore()?.shop;
}
export function getRequestTenantId(): string | undefined {
  return requestStore.getStore()?.tenantId;
}
export function setRequestTenantId(tenantId: string): void {
  const store = requestStore.getStore();
  if (store) store.tenantId = tenantId;
}
export function setRequestShop(shop: string): void {
  const store = requestStore.getStore();
  if (store) store.shop = shop;
}
export function requestIdFromHeaders(request: Request): string {
  return request.headers.get("X-Request-Id") || randomUUID();
}

/**
 * Wrap a code path in the request context. If one is already active (established
 * by requestContextMiddleware), reuse it — only enrich the shop — so we never nest
 * a second store with a divergent requestId or emit duplicate ui.request.* logs.
 */
export async function withRequestContext<T>(
  request: Request,
  shop: string | undefined,
  fn: () => Promise<T>,
): Promise<T> {
  if (getRequestId()) {
    if (shop) setRequestShop(shop);
    return fn();
  }
  const started = performance.now();
  return runWithRequestContext({ requestId: requestIdFromHeaders(request), shop }, async () => {
    logUiRequestReceived(request);
    try {
      const result = await fn();
      return logUiRequestFinished(request, started, result) as T;
    } catch (error) {
      if (!isRedirectResponse(error)) logUiRequestFailed(request, started, error);
      throw error;
    }
  });
}

/** Root-route middleware (wired in app/root.tsx). Gives the entire matched route
 *  tree one request-scoped context + the ui.request.* lifecycle logs + the
 *  X-Request-Id response header. Requires future.v8_middleware. */
export const requestContextMiddleware: MiddlewareFunction<Response> = async ({ request }, next) => {
  const started = performance.now();
  return runWithRequestContext({ requestId: requestIdFromHeaders(request) }, async () => {
    logUiRequestReceived(request);
    try {
      const response = await next();
      logUiRequestFinished(request, started, response);
      return response;
    } catch (error) {
      if (!isRedirectResponse(error)) logUiRequestFailed(request, started, error);
      throw error;
    }
  });
};
