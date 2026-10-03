import { test } from "node:test";
import assert from "node:assert/strict";
import {
  verifiedRedirectHint,
  billingRedirectHints,
  isFullPageLoad,
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

test("only the admin's own page load (?embedded=1) is redirected on the server", () => {
  assert.equal(isFullPageLoad(new URL("https://app.example/app/billing?embedded=1&shop=s")), true);
  assert.equal(isFullPageLoad(new URL("https://app.example/app/billing.data")), false);
});

test("the plan in Shopify's redirect counts only when Shopify shows that subscription active", () => {
  const active = [{ id: "gid://shopify/AppSubscription/123", status: "ACTIVE" }];
  assert.deepEqual(verifiedRedirectHint({ planHandle: "light", chargeId: "123" }, active), {
    plan_handle: "light",
    charge_id: "123",
  });
  assert.deepEqual(verifiedRedirectHint({ planHandle: "light", chargeId: null }, active), {
    plan_handle: "light",
    charge_id: null,
  });
  // A replayed or hand-made URL: no active subscription, or another charge.
  assert.equal(verifiedRedirectHint({ planHandle: "light", chargeId: "123" }, []), null);
  assert.equal(verifiedRedirectHint({ planHandle: "light", chargeId: "999" }, active), null);
  assert.equal(
    verifiedRedirectHint({ planHandle: "light", chargeId: "123" }, [{ id: "gid://shopify/AppSubscription/123", status: "CANCELLED" }]),
    null,
  );
  assert.equal(verifiedRedirectHint({ planHandle: null, chargeId: "123" }, active), null);
});
