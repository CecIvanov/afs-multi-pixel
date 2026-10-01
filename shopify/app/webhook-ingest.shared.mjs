// Topic helpers, duplicated intentionally on both the Node and Python sides so
// normalization + idempotency agree. Pure functions — unit-testable.

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
 * `authenticate` is `shopify.authenticate.webhook`; on a bad HMAC it throws a 401
 * Response, which propagates untouched. A failed store answers 500 so Shopify
 * redelivers.
 *
 * @param {Request} request
 * @param {{
 *   authenticate: (request: Request) => Promise<{ shop: string, topic: string, payload?: unknown, session?: any }>,
 *   ingest: (params: { shop: string, topic: string, webhookId: string | null, payload?: Record<string, unknown>, webhookContext?: Record<string, unknown> }) => Promise<unknown>,
 *   withContext?: <T>(request: Request, shop: string, fn: () => Promise<T>) => Promise<T>,
 *   logInfo?: (event: string, fields?: Record<string, unknown>) => void,
 *   logError?: (event: string, error: unknown, fields?: Record<string, unknown>) => void,
 * }} deps
 * @returns {Promise<Response>}
 */
export async function receiveWebhook(request, deps) {
  const { authenticate, ingest, withContext = (_request, _shop, fn) => fn(), logInfo = () => {}, logError = () => {} } = deps;
  const verified = await authenticate(request);
  const { shop, payload, session } = verified;
  // The header is the exact topic ("app/scopes_update"); authenticate returns the
  // lossy storage form ("APP_SCOPES_UPDATE").
  const topic = request.headers.get("X-Shopify-Topic") || verified.topic;
  const webhookId = request.headers.get("X-Shopify-Webhook-Id");

  return withContext(request, shop, async () => {
    logInfo("shopify.webhook.received", { topic, shop });
    try {
      await ingest({
        shop,
        topic,
        webhookId,
        payload: /** @type {Record<string, unknown> | undefined} */ (payload),
        webhookContext: webhookContextFor(topic, payload, session),
      });
    } catch (error) {
      logError("shopify.webhook.ingest_failed", error, { shop, topic });
      return new Response("Webhook ingest failed", { status: 500 });
    }
    return new Response();
  });
}

/**
 * app/scopes_update carries the session token + new scopes so the worker can
 * persist them on the tenant. Every other topic needs nothing beyond its payload.
 *
 * @param {string} topic
 * @param {any} payload
 * @param {any} session
 * @returns {Record<string, unknown> | undefined}
 */
function webhookContextFor(topic, payload, session) {
  if (normalizeWebhookTopic(topic) !== "app/scopes_update" || !session?.accessToken) return undefined;
  return {
    access_token: session.accessToken,
    scopes: ((payload?.current ?? [])).join(","),
    refresh_token: session.refreshToken ?? undefined,
    access_token_expires_at: session.expires?.toISOString(),
    refresh_token_expires_at: session.refreshTokenExpires?.toISOString(),
  };
}
