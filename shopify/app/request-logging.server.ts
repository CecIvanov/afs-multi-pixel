import { createLogger } from "../../packages/logger/src/index.ts";
import { getRequestId, getRequestShop } from "./request-context.server.ts";

const uiRequestLogger = createLogger({
  baseContext: { component: "ui", service: "ui", env: process.env.APP_ENV ?? "development" },
});

const UI_QUIET_PATHS = new Set(["/", "/healthz", "/metrics"]);

export function roundMs(started: number): number {
  return Math.round((performance.now() - started) * 10) / 10;
}
export function requestPath(request: Request): string {
  return new URL(request.url).pathname;
}
export function shouldSkipUiRequestLog(path: string, method: string): boolean {
  if (method === "OPTIONS") return true;
  return method === "GET" && UI_QUIET_PATHS.has(path);
}

function contextualFields(fields: Record<string, unknown> = {}): Record<string, unknown> {
  const requestId = getRequestId();
  const shop = getRequestShop();
  return {
    ...(requestId ? { requestId } : {}),
    ...(shop ? { shop } : {}),
    ...fields,
  };
}

export function logUiRequestReceived(request: Request) {
  const path = requestPath(request);
  if (shouldSkipUiRequestLog(path, request.method)) return;
  uiRequestLogger.info("ui.request.received", contextualFields({ method: request.method, path }));
}

export function logUiRequestFinished(request: Request, started: number, result: unknown) {
  const path = requestPath(request);
  if (shouldSkipUiRequestLog(path, request.method)) return result;

  const durationMs = roundMs(started);
  const status = result instanceof Response ? result.status : 200;
  const ctx = contextualFields({ method: request.method, path, status, durationMs });
  if (status >= 500) uiRequestLogger.error("ui.request.completed", new Error(`HTTP ${status}`), ctx);
  else if (status >= 400) uiRequestLogger.warn("ui.request.completed", ctx);
  else uiRequestLogger.info("ui.request.completed", ctx);

  if (result instanceof Response) {
    const requestId = getRequestId();
    if (requestId) result.headers.set("X-Request-Id", requestId);
  }
  return result;
}

export function logUiRequestFailed(request: Request, started: number, error: unknown) {
  const path = requestPath(request);
  if (shouldSkipUiRequestLog(path, request.method)) return;
  uiRequestLogger.error(
    "ui.request.failed",
    error,
    contextualFields({ method: request.method, path, durationMs: roundMs(started) }),
  );
}
