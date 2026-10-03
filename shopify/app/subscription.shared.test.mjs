import { test } from "node:test";
import assert from "node:assert/strict";
import {
  billingRedirectHints,
  requiresPlanSelection,
  returnedFromShopifyBilling,
  shouldReuseCheck,
} from "./subscription.shared.mjs";

test("billingRedirectHints reads what Shopify adds after the merchant picks a plan", () => {
  const back = billingRedirectHints(new URL("https://app.example/app?shop=s&plan_handle=Light&charge_id=123"));
  assert.deepEqual(back, { planHandle: "light", chargeId: "123" });
  assert.equal(returnedFromShopifyBilling(back), true);

  const plain = billingRedirectHints(new URL("https://app.example/app?shop=s"));
  assert.deepEqual(plain, { planHandle: null, chargeId: null });
  assert.equal(returnedFromShopifyBilling(plain), false);
  assert.equal(returnedFromShopifyBilling({ planHandle: null, chargeId: "123" }), true);
});

test("a shop goes to Shopify's plan page until a plan is stored", () => {
  assert.equal(requiresPlanSelection({ billingEnabled: true, subscribed: false }), true);
  assert.equal(requiresPlanSelection({ billingEnabled: true, subscribed: true }), false);
  assert.equal(requiresPlanSelection({ billingEnabled: false, subscribed: false }), false);
});

test("a recent check is reused unless the merchant just came back from billing", () => {
  const base = { cachedAt: 1_000, ttlMs: 300_000 };
  assert.equal(shouldReuseCheck({ ...base, now: 2_000, forceFresh: false }), true);
  assert.equal(shouldReuseCheck({ ...base, now: 2_000, forceFresh: true }), false);
  assert.equal(shouldReuseCheck({ ...base, now: 302_000, forceFresh: false }), false);
  assert.equal(shouldReuseCheck({ cachedAt: null, ttlMs: 300_000, now: 2_000, forceFresh: false }), false);
});
