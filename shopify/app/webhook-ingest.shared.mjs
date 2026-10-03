// Topic helpers, duplicated intentionally on both the Node and Python sides so
// normalization + idempotency agree. Pure functions — unit-testable.

import { createHmac, timingSafeEqual } from "node:crypto";

/** Topics that must return HTTP 2xx to Shopify even when the tenant is unknown. */
export const IDEMPOTENT_WEBHOOK_TOPICS = new Set([
  "app/uninstalled",
  "shop/redact",
  "customers/data_request",
  "customers/redact",
]);

/**
 * "app/scopes_update" stays as is; the storage form "APP_SCOPES_UPDATE" that
 * authenticate.webhook returns becomes "app/scopes_update" — only the first
 * underscore is the resource separator.
 *
 * @param {string | null | undefined} topic
 */
export function normalizeWebhookTopic(topic) {
  const raw = String(topic || "").trim().toLowerCase();
  if (!raw) return "";
  return raw.includes("/") ? raw : raw.replace("_", "/");
}

/** @param {string | null | undefined} topic */
export function isIdempotentWebhookTopic(topic) {
  return IDEMPOTENT_WEBHOOK_TOPICS.has(normalizeWebhookTopic(topic));
}

/**
 * The whole job of every webhook route: verify the HMAC, store the webhook in the
 * backend inbox, answer. No handler work happens here — the backend worker does it.
 *
 * Shopify's `authenticate.webhook` is NOT used: it loads the shop's offline
 * session and, with expiring offline tokens, refreshes an expired token before
 * any topic — which Shopify refuses once the app is uninstalled, so uninstall and
 * redact webhooks answered 500. Storing a webhook needs no session or token; the
 * worker reads whatever it needs.
 *
 * A bad HMAC answers 401; a failed store answers 500 so Shopify redelivers.
 *
 * @param {Request} request
 * @param {{
 *   apiSecretKey: string,
 *   ingest: (params: { shop: string, topic: string, webhookId: string | null, triggeredAt: string | null, payload?: Record<string, unknown> }) => Promise<unknown>,
 *   withContext?: <T>(request: Request, shop: string, fn: () => Promise<T>) => Promise<T>,
 *   logInfo?: (event: string, fields?: Record<string, unknown>) => void,
 *   logError?: (event: string, error: unknown, fields?: Record<string, unknown>) => void,
 * }} deps
 * @returns {Promise<Response>}
 */
export async function receiveWebhook(request, deps) {
  const {
    apiSecretKey,
    ingest,
    withContext = (_request, _shop, fn) => fn(),
    logInfo = () => {},
    logError = () => {},
  } = deps;
  if (request.method !== "POST") return new Response(undefined, { status: 405 });
  const rawBody = await request.text();
  if (!hasValidHmac(rawBody, request.headers.get("X-Shopify-Hmac-Sha256"), apiSecretKey)) {
    return new Response(undefined, { status: 401, statusText: "Unauthorized" });
  }
  const shop = request.headers.get("X-Shopify-Shop-Domain") || "";
  const topic = request.headers.get("X-Shopify-Topic") || "";
  const webhookId = request.headers.get("X-Shopify-Webhook-Id");
  // When Shopify fired it: lets the worker tell a stale app/uninstalled from a reinstall.
  const triggeredAt = request.headers.get("X-Shopify-Triggered-At");
  let payload;
  try {
    payload = rawBody ? JSON.parse(rawBody) : undefined;
  } catch {
    return new Response(undefined, { status: 400, statusText: "Bad Request" });
  }

  return withContext(request, shop, async () => {
    logInfo("shopify.webhook.received", { topic, shop });
    try {
      await ingest({
        shop,
        topic,
        webhookId,
        triggeredAt,
        payload: /** @type {Record<string, unknown> | undefined} */ (payload),
      });
    } catch (error) {
      logError("shopify.webhook.ingest_failed", error, { shop, topic });
      return new Response("Webhook ingest failed", { status: 500 });
    }
    return new Response();
  });
}

/**
 * Shopify signs the raw body with the app secret (base64 HMAC-SHA256).
 *
 * @param {string} rawBody
 * @param {string | null} given
 * @param {string} secret
 */
export function hasValidHmac(rawBody, given, secret) {
  if (!secret || !given) return false;
  const expected = Buffer.from(createHmac("sha256", secret).update(rawBody, "utf8").digest("base64"), "utf8");
  const actual = Buffer.from(given, "utf8");
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}
