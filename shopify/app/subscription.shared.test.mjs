import { test } from "node:test";
import assert from "node:assert/strict";
import { honoursRedirectHint, planHandleHint, shouldReuseCheck } from "./subscription.shared.mjs";

test("the redirect after choosing a plan lets the merchant in while the Partner API catches up", () => {
  assert.equal(honoursRedirectHint(true, null), true);
  assert.equal(honoursRedirectHint(false, null), false);
  assert.equal(honoursRedirectHint(false, "shopify-test"), true);
  assert.equal(honoursRedirectHint(false, "none"), false);
});

test("planHandleHint reads Shopify's redirect after the merchant picks a plan", () => {
  assert.equal(planHandleHint(new URL("https://app.example/app?shop=s&plan_handle=light")), "light");
  assert.equal(planHandleHint(new URL("https://app.example/app?shop=s")), null);
});

test("a recent check is reused unless the merchant just came back from billing", () => {
  const base = { cachedAt: 1_000, ttlMs: 300_000 };
  assert.equal(shouldReuseCheck({ ...base, now: 2_000, forceFresh: false }), true);
  assert.equal(shouldReuseCheck({ ...base, now: 2_000, forceFresh: true }), false);
  assert.equal(shouldReuseCheck({ ...base, now: 302_000, forceFresh: false }), false);
  assert.equal(shouldReuseCheck({ cachedAt: null, ttlMs: 300_000, now: 2_000, forceFresh: false }), false);
});
