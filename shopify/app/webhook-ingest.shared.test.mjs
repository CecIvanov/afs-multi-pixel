import { test } from "node:test";
import assert from "node:assert/strict";
import {
  isIdempotentWebhookTopic,
  normalizeWebhookTopic,
} from "./webhook-ingest.shared.mjs";

test("normalizeWebhookTopic handles both slash and underscore forms", () => {
  assert.equal(normalizeWebhookTopic("APP/UNINSTALLED"), "app/uninstalled");
  assert.equal(normalizeWebhookTopic("app_uninstalled"), "app/uninstalled");
  assert.equal(normalizeWebhookTopic("customers_redact"), "customers/redact");
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
