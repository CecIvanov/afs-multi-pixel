import assert from "node:assert/strict";
import test from "node:test";

import { resolveEmbeddedAuthRecovery } from "./auth-recovery.shared.mjs";

test("redirects into /app when Shopify launch params are present", () => {
  const result = resolveEmbeddedAuthRecovery({
    search: "?shop=demo.myshopify.com&host=abc&embedded=1",
    distribution: "SingleMerchant",
  });
  assert.equal(result.kind, "redirect");
  assert.equal(result.to, "/app?shop=demo.myshopify.com&host=abc&embedded=1");
  assert.equal(result.signals.hasLaunchParams, true);
});

test("redirects into /app when a Bearer session token is present", () => {
  const result = resolveEmbeddedAuthRecovery({
    search: "",
    headers: { Authorization: "Bearer abc.def.ghi" },
    distribution: "AppStore",
  });
  assert.equal(result.kind, "redirect");
  assert.equal(result.to, "/app");
  assert.equal(result.signals.bearer, true);
});

test("SingleMerchant with no params re-embeds via App Bridge (never the login form)", () => {
  const result = resolveEmbeddedAuthRecovery({
    search: "",
    distribution: "SingleMerchant",
  });
  assert.equal(result.kind, "app-bridge");
  assert.equal(result.signals.embeddedOnly, true);
});

test("ShopifyAdmin distribution also re-embeds via App Bridge", () => {
  const result = resolveEmbeddedAuthRecovery({
    search: "",
    distribution: "shopify-admin",
  });
  assert.equal(result.kind, "app-bridge");
});

test("AppStore, not framed, no params falls back to the shop-domain form", () => {
  const result = resolveEmbeddedAuthRecovery({
    search: "",
    distribution: "AppStore",
  });
  assert.equal(result.kind, "form");
  assert.equal(result.signals.embeddedOnly, false);
  assert.equal(result.signals.framed, false);
});

test("AppStore inside an iframe (Sec-Fetch-Dest) re-embeds via App Bridge", () => {
  const headers = new Headers({ "Sec-Fetch-Dest": "iframe" });
  const result = resolveEmbeddedAuthRecovery({
    search: "",
    headers,
    distribution: "AppStore",
  });
  assert.equal(result.kind, "app-bridge");
  assert.equal(result.signals.framed, true);
});

test("AppStore with an admin.shopify.com referer re-embeds via App Bridge", () => {
  const result = resolveEmbeddedAuthRecovery({
    search: "",
    headers: { referer: "https://admin.shopify.com/store/demo/apps/bg-delivery" },
    distribution: "AppStore",
  });
  assert.equal(result.kind, "app-bridge");
  assert.equal(result.signals.framed, true);
});

test("plain top-level browser request (no iframe signal) shows the form for AppStore", () => {
  const result = resolveEmbeddedAuthRecovery({
    search: "",
    headers: new Headers({ "Sec-Fetch-Dest": "document" }),
    distribution: "AppStore",
  });
  assert.equal(result.kind, "form");
});
