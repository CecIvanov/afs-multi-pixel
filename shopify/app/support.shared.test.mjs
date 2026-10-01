import { test } from "node:test";
import assert from "node:assert/strict";
import {
  isTruthy,
  isViberFabEnabled,
  supportViberChatUrl,
  viberFabAnchorAttrs,
} from "./support.shared.mjs";

test("supportViberChatUrl builds a viber:// deep link from digits only", () => {
  assert.equal(supportViberChatUrl("+1 555 000 0000"), "viber://chat?number=15550000000");
  assert.equal(supportViberChatUrl("359883380656"), "viber://chat?number=359883380656");
  assert.equal(supportViberChatUrl(""), "");
});

test("isViberFabEnabled requires an explicit flag AND a number", () => {
  assert.equal(isViberFabEnabled({ enabled: "true", numberE164: "15550000000" }), true);
  assert.equal(isViberFabEnabled({ enabled: "false", numberE164: "15550000000" }), false);
  assert.equal(isViberFabEnabled({ enabled: "true", numberE164: "" }), false); // no number
  assert.equal(isViberFabEnabled({}), false);
});

test("isTruthy accepts common truthy env strings", () => {
  for (const v of ["1", "true", "yes", "on", "TRUE"]) assert.equal(isTruthy(v), true, v);
  for (const v of ["0", "false", "", "no", undefined]) assert.equal(isTruthy(v), false, String(v));
});

test("viberFabAnchorAttrs opens safely in a throwaway context", () => {
  const attrs = viberFabAnchorAttrs("15550000000");
  assert.equal(attrs.target, "_blank");
  assert.equal(attrs.rel, "noopener noreferrer");
  assert.equal(attrs.href, "viber://chat?number=15550000000");
});
