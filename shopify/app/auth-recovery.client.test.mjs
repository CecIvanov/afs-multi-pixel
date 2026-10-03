import assert from "node:assert/strict";
import test from "node:test";

import { recoverEmbeddedAdminAuth, waitForShopifyGlobal } from "./auth-recovery.client.mjs";
import { buildSessionTokenBouncePath } from "./auth-recovery.shared.mjs";

test("buildSessionTokenBouncePath mirrors the library bounce URL shape", () => {
  const path = buildSessionTokenBouncePath({
    shop: "demo.myshopify.com",
    host: "abc123",
    appOrigin: "https://example.com",
  });

  const url = new URL(path, "https://example.com");
  assert.equal(url.pathname, "/auth/session-token");
  assert.equal(url.searchParams.get("shop"), "demo.myshopify.com");
  assert.equal(url.searchParams.get("host"), "abc123");
  assert.equal(url.searchParams.get("embedded"), "1");
  assert.equal(
    url.searchParams.get("shopify-reload"),
    "https://example.com/app?shop=demo.myshopify.com&host=abc123&embedded=1",
  );
});

test("recoverEmbeddedAdminAuth redirects to /app when launch params are already present", async () => {
  let assigned = "";
  const result = await recoverEmbeddedAdminAuth(
    {
      location: {
        origin: "https://example.com",
        search: "?shop=demo.myshopify.com&host=abc123&embedded=1",
        assign(url) {
          assigned = url;
        },
      },
    },
    { appPath: "/app" },
  );

  assert.equal(result.outcome, "redirect_launch_params");
  assert.equal(
    assigned,
    "https://example.com/app?shop=demo.myshopify.com&host=abc123&embedded=1",
  );
});

test("recoverEmbeddedAdminAuth bounces through /auth/session-token using App Bridge config", async () => {
  let assigned = "";
  const shopify = {
    ready: Promise.resolve(),
    config: {
      shop: "demo.myshopify.com",
      host: "abc123",
    },
  };

  const result = await recoverEmbeddedAdminAuth(
    {
      shopify,
      location: {
        origin: "https://example.com",
        search: "",
        assign(url) {
          assigned = url;
        },
      },
      setTimeout(fn) {
        fn();
      },
    },
    { appPath: "/app", timeoutMs: 100 },
  );

  assert.equal(result.outcome, "bounce");
  assert.match(assigned, /^\/auth\/session-token\?/);
  assert.match(assigned, /shopify-reload=/);
});

test("waitForShopifyGlobal resolves once the global appears", async () => {
  let shopify;
  const timers = [];
  const promise = waitForShopifyGlobal(
    {
      get shopify() {
        return shopify;
      },
      setTimeout(fn, ms) {
        timers.push({ fn, ms });
        return timers.length;
      },
    },
    200,
    10,
  );

  shopify = { ready: Promise.resolve() };
  for (const timer of timers) {
    timer.fn();
  }

  assert.equal(await promise, shopify);
});
