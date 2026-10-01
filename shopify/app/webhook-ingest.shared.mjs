// Topic helpers, duplicated intentionally on both the Node and Python sides so
// normalization + idempotency agree. Pure functions — unit-testable.

/** Topics that must return HTTP 2xx to Shopify even when the tenant is unknown. */
export const IDEMPOTENT_WEBHOOK_TOPICS = new Set([
  "app/uninstalled",
  "shop/redact",
  "customers/data_request",
  "customers/redact",
]);

/** @param {string | null | undefined} topic */
export function normalizeWebhookTopic(topic) {
  const raw = String(topic || "").trim();
  if (!raw) return "";
  return raw.includes("/") ? raw.toLowerCase() : raw.toLowerCase().replaceAll("_", "/");
}

/** @param {string | null | undefined} topic */
export function isIdempotentWebhookTopic(topic) {
  return IDEMPOTENT_WEBHOOK_TOPICS.has(normalizeWebhookTopic(topic));
}
