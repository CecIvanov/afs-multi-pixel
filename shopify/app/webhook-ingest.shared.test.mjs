import { test } from "node:test";
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import "@shopify/shopify-app-react-router/adapters/node";
import { ApiVersion, shopifyApp } from "@shopify/shopify-app-react-router/server";
import {
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
const noSessions = {
  storeSession: async () => true,
  loadSession: async () => undefined,
  deleteSession: async () => true,
  deleteSessions: async () => true,
  findSessionsByShop: async () => [],
};
const { authenticate } = shopifyApp({
  apiKey: "test-key",
  apiSecretKey: SECRET,
  apiVersion: ApiVersion.October26,
  appUrl: "https://app.test",
  sessionStorage: noSessions,
  isTesting: true,
});

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

test("receiveWebhook rejects a bad HMAC with 401 and stores nothing", async () => {
  const { calls, ingest } = recordingIngest();
  const response = await receiveWebhook(webhookRequest({ hmac: "not-the-hmac" }), {
    authenticate: authenticate.webhook,
    ingest,
  }).catch((thrown) => thrown);
  assert.ok(response instanceof Response);
  assert.equal(response.status, 401);
  assert.equal(calls.length, 0);
});

test("receiveWebhook stores a verified webhook with its Shopify ID and answers 200", async () => {
  const { calls, ingest } = recordingIngest();
  const request = webhookRequest({ topic: "customers/data_request" });
  const response = await receiveWebhook(request, { authenticate: authenticate.webhook, ingest });
  assert.equal(response.status, 200);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].shop, "shop-a.myshopify.com");
  assert.equal(calls[0].topic, "customers/data_request"); // the exact header, not CUSTOMERS_DATA_REQUEST
  assert.equal(calls[0].webhookId, "wh-123");
  assert.deepEqual(calls[0].payload, { orders_to_redact: [1] });
});

test("receiveWebhook answers 500 when the webhook could not be stored, so Shopify redelivers", async () => {
  const response = await receiveWebhook(webhookRequest(), {
    authenticate: authenticate.webhook,
    ingest: async () => {
      throw new Error("backend down");
    },
  });
  assert.equal(response.status, 500);
});

test("receiveWebhook passes the session token along on app/scopes_update", async () => {
  const { calls, ingest } = recordingIngest();
  const fakeAuthenticate = async () => ({
    shop: "shop-a.myshopify.com",
    topic: "APP_SCOPES_UPDATE",
    payload: { current: ["read_markets", "read_orders"] },
    session: { accessToken: "shpat_1", refreshToken: "rt_1", expires: new Date("2026-10-02T00:00:00Z") },
  });
  await receiveWebhook(webhookRequest({ topic: "app/scopes_update" }), { authenticate: fakeAuthenticate, ingest });
  assert.deepEqual(calls[0].webhookContext, {
    access_token: "shpat_1",
    scopes: "read_markets,read_orders",
    refresh_token: "rt_1",
    access_token_expires_at: "2026-10-02T00:00:00.000Z",
    refresh_token_expires_at: undefined,
  });
});
