import { test } from "node:test";
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import {
  hasValidHmac,
  isIdempotentWebhookTopic,
  normalizeWebhookTopic,
  receiveWebhook,
} from "./webhook-ingest.shared.mjs";

test("normalizeWebhookTopic handles both slash and underscore forms", () => {
  assert.equal(normalizeWebhookTopic("APP/UNINSTALLED"), "app/uninstalled");
  assert.equal(normalizeWebhookTopic("app_uninstalled"), "app/uninstalled");
  assert.equal(normalizeWebhookTopic("customers_redact"), "customers/redact");
  // authenticate.webhook's storage form: only the first underscore is the separator.
  assert.equal(normalizeWebhookTopic("APP_SCOPES_UPDATE"), "app/scopes_update");
  assert.equal(normalizeWebhookTopic("CUSTOMERS_DATA_REQUEST"), "customers/data_request");
  assert.equal(normalizeWebhookTopic(""), "");
  assert.equal(normalizeWebhookTopic(null), "");
});

test("isIdempotentWebhookTopic flags lifecycle + compliance topics", () => {
  for (const t of ["app/uninstalled", "shop/redact", "customers/data_request", "customers/redact"]) {
    assert.equal(isIdempotentWebhookTopic(t), true, t);
  }
  assert.equal(isIdempotentWebhookTopic("app/scopes_update"), false);
  assert.equal(isIdempotentWebhookTopic("orders/create"), false);
});

// --- receiveWebhook: verify, store, answer -----------------------------------
const SECRET = "test-secret";

function webhookRequest({ topic = "customers/redact", body = { orders_to_redact: [1] }, hmac } = {}) {
  const raw = JSON.stringify(body);
  return new Request(`https://app.test/webhooks/${topic}`, {
    method: "POST",
    body: raw,
    headers: {
      "Content-Type": "application/json",
      "X-Shopify-Hmac-Sha256": hmac ?? createHmac("sha256", SECRET).update(raw).digest("base64"),
      "X-Shopify-Topic": topic,
      "X-Shopify-Shop-Domain": "shop-a.myshopify.com",
      "X-Shopify-Webhook-Id": "wh-123",
      "X-Shopify-API-Version": "2026-10",
      "X-Shopify-Triggered-At": "2026-10-03T12:08:29.346Z",
    },
  });
}

function recordingIngest() {
  const calls = [];
  const ingest = async (params) => {
    calls.push(params);
  };
  return { calls, ingest };
}

test("hasValidHmac checks Shopify's signature of the raw body", () => {
  const sig = createHmac("sha256", SECRET).update("{}").digest("base64");
  assert.equal(hasValidHmac("{}", sig, SECRET), true);
  assert.equal(hasValidHmac('{"a":1}', sig, SECRET), false);
  assert.equal(hasValidHmac("{}", sig, ""), false);
  assert.equal(hasValidHmac("{}", null, SECRET), false);
});

test("receiveWebhook rejects a bad HMAC with 401 and stores nothing", async () => {
  const { calls, ingest } = recordingIngest();
  const response = await receiveWebhook(webhookRequest({ hmac: "not-the-hmac" }), { apiSecretKey: SECRET, ingest });
  assert.equal(response.status, 401);
  assert.equal(calls.length, 0);
});

test("receiveWebhook stores a verified webhook with its Shopify ID and answers 200", async () => {
  const { calls, ingest } = recordingIngest();
  const response = await receiveWebhook(webhookRequest({ topic: "customers/data_request" }), {
    apiSecretKey: SECRET,
    ingest,
  });
  assert.equal(response.status, 200);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].shop, "shop-a.myshopify.com");
  assert.equal(calls[0].topic, "customers/data_request");
  assert.equal(calls[0].webhookId, "wh-123");
  assert.deepEqual(calls[0].payload, { orders_to_redact: [1] });
});

test("receiveWebhook answers 500 when the webhook could not be stored, so Shopify redelivers", async () => {
  const response = await receiveWebhook(webhookRequest(), {
    apiSecretKey: SECRET,
    ingest: async () => {
      throw new Error("backend down");
    },
  });
  assert.equal(response.status, 500);
});

test("every verified topic is just stored and answered 200 — no session, no token", async () => {
  for (const topic of ["app/uninstalled", "shop/redact", "customers/redact", "customers/data_request", "app/scopes_update", "orders/create"]) {
    const { calls, ingest } = recordingIngest();
    const response = await receiveWebhook(webhookRequest({ topic, body: { id: 1 } }), { apiSecretKey: SECRET, ingest });
    assert.equal(response.status, 200, topic);
    assert.deepEqual(
      calls,
      [{ shop: "shop-a.myshopify.com", topic, webhookId: "wh-123", triggeredAt: "2026-10-03T12:08:29.346Z", payload: { id: 1 } }],
      topic,
    );
  }
});
