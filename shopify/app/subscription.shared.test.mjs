import { test } from "node:test";
import assert from "node:assert/strict";
import { isSubscribed, planHandleHint, shouldReuseCheck } from "./subscription.shared.mjs";

const snapshot = (over = {}) => ({ has_active_contract: true, effective_plan_handle: "light", ...over });

test("only an active contract on the exact plan handle counts", () => {
  assert.equal(isSubscribed(snapshot(), "light"), true);
  assert.equal(isSubscribed(snapshot({ effective_plan_handle: "LIGHT" }), "light"), true);
  assert.equal(isSubscribed(snapshot({ effective_plan_handle: "pro" }), "light"), false);
  assert.equal(isSubscribed(snapshot({ has_active_contract: false }), "light"), false);
  assert.equal(isSubscribed(null, "light"), false);
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
