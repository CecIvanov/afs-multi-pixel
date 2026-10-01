import { test } from "node:test";
import assert from "node:assert/strict";
import {
  BackendRequestError,
  isBackendTenantNotFoundError,
  isRedirectResponse,
  parseBackendErrorDetail,
  shouldLogBackendRequestFailure,
} from "./backend-fetch.helpers.mjs";

test("parseBackendErrorDetail extracts detail/message from JSON", () => {
  assert.equal(parseBackendErrorDetail('{"detail":"nope"}'), "nope");
  assert.equal(parseBackendErrorDetail('{"message":"boom"}'), "boom");
  assert.equal(parseBackendErrorDetail("plain text"), "plain text");
  assert.equal(parseBackendErrorDetail(""), "");
});

test("isBackendTenantNotFoundError matches 404 / TENANT_NOT_FOUND", () => {
  assert.equal(isBackendTenantNotFoundError(new BackendRequestError(404, "x")), true);
  assert.equal(
    isBackendTenantNotFoundError(new BackendRequestError(500, "x", { code: "TENANT_NOT_FOUND" })),
    true,
  );
  assert.equal(isBackendTenantNotFoundError(new BackendRequestError(500, "x")), false);
  assert.equal(isBackendTenantNotFoundError(new Error("plain")), false);
});

test("shouldLogBackendRequestFailure skips handled 404s", () => {
  assert.equal(shouldLogBackendRequestFailure(404, ""), false);
  assert.equal(shouldLogBackendRequestFailure(500, ""), true);
});

test("isRedirectResponse detects 3xx Responses only", () => {
  assert.equal(isRedirectResponse(new Response(null, { status: 302 })), true);
  assert.equal(isRedirectResponse(new Response(null, { status: 200 })), false);
  assert.equal(isRedirectResponse(new Error("x")), false);
});
