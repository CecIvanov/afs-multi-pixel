import { test } from "node:test";
import assert from "node:assert/strict";
import { hasActivePlan } from "./subscription.shared.mjs";

test("only an ACTIVE subscription to the exact plan name counts", () => {
  const plan = "AFS Multi Pixel";
  assert.equal(hasActivePlan([{ name: plan, status: "ACTIVE" }], plan), true);
  assert.equal(hasActivePlan([{ name: plan, status: "PENDING" }], plan), false);
  assert.equal(hasActivePlan([{ name: "AFS Multi Pixel Pro", status: "ACTIVE" }], plan), false);
  assert.equal(hasActivePlan([], plan), false);
  assert.equal(hasActivePlan(null, plan), false);
});
