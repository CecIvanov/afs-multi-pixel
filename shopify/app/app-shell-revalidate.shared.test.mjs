import { test } from "node:test";
import assert from "node:assert/strict";
import { hasBillingRedirectParams, isMutation, shouldRevalidateAppShell } from "./app-shell-revalidate.shared.mjs";

const nav = (from, to, extra = {}) =>
  shouldRevalidateAppShell({
    currentPathname: from,
    nextPathname: to,
    nextSearchParams: new URLSearchParams(),
    ...extra,
  });

test("isMutation: only non-GET submissions", () => {
  assert.equal(isMutation(undefined), false);
  assert.equal(isMutation("GET"), false);
  assert.equal(isMutation("post"), true);
});

test("hasBillingRedirectParams: Shopify's return from the plan page", () => {
  assert.equal(hasBillingRedirectParams(new URLSearchParams("plan_handle=light")), true);
  assert.equal(hasBillingRedirectParams(new URLSearchParams("charge_id=1")), true);
  assert.equal(hasBillingRedirectParams(new URLSearchParams("shop=s")), false);
});

test("a plain navigation between pages doesn't re-run the shell", () => {
  assert.equal(nav("/app", "/app/markets/1"), false);
  assert.equal(nav("/app/markets/1", "/app/help"), false);
});

test("a save always re-runs the shell", () => {
  assert.equal(nav("/app/markets/1", "/app/markets/1", { formMethod: "POST" }), true);
  assert.equal(nav("/app/markets/1", "/app", { formMethod: "POST" }), true);
});

test("back from Shopify billing always re-runs the shell", () => {
  assert.equal(nav("/app/help", "/app", { nextSearchParams: new URLSearchParams("plan_handle=light") }), true);
});

test("same path follows the framework default", () => {
  assert.equal(nav("/app", "/app", { defaultShouldRevalidate: true }), true);
  assert.equal(nav("/app", "/app", { defaultShouldRevalidate: false }), false);
});
