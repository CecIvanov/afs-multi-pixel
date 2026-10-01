import { test } from "node:test";
import assert from "node:assert/strict";
import { classifyChange, normalizeShopifyPlanName, rankOf } from "./billing.shared.mjs";

// Mirrors app.config.json billing.plans (the parity fixture).
const PLANS = [
  { handle: "free", name: "Free", rank: 0, shopifyPlanName: null },
  { handle: "pro", name: "Pro", rank: 10, shopifyPlanName: "Pro" },
];

test("rankOf reads plan rank, defaults 0", () => {
  assert.equal(rankOf(PLANS, "free"), 0);
  assert.equal(rankOf(PLANS, "pro"), 10);
  assert.equal(rankOf(PLANS, "nope"), 0);
});

test("classifyChange matches the Python semantics", () => {
  assert.equal(classifyChange(PLANS, "free", "pro"), "upgrade");
  assert.equal(classifyChange(PLANS, "pro", "free"), "downgrade");
  assert.equal(classifyChange(PLANS, "free", "free"), "same");
});

test("normalizeShopifyPlanName maps names/display back to handles", () => {
  assert.equal(normalizeShopifyPlanName(PLANS, "Pro"), "pro");
  assert.equal(normalizeShopifyPlanName(PLANS, "free"), "free");
  assert.equal(normalizeShopifyPlanName(PLANS, "MyApp Pro"), "pro");
  assert.equal(normalizeShopifyPlanName(PLANS, "nonsense"), null);
});
