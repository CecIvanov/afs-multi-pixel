import { buildSessionTokenBouncePath } from "./auth-recovery.shared.mjs";

/**
 * @param {Window & { shopify?: { ready?: Promise<void>; config?: { shop?: string; host?: string } } }} windowLike
 * @param {number} [timeoutMs]
 * @param {number} [pollMs]
 */
export async function waitForShopifyGlobal(windowLike, timeoutMs = 15000, pollMs = 50) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (windowLike.shopify) {
      return windowLike.shopify;
    }
    await new Promise((resolve) => {
      windowLike.setTimeout(resolve, pollMs);
    });
  }
  return null;
}

/**
 * Recover an embedded admin session after a bare `/auth/login` or `/` load.
 *
 * @param {Window & { shopify?: { ready?: Promise<void>; config?: { shop?: string; host?: string } } }} windowLike
 * @param {{ appPath?: string; timeoutMs?: number }} [options]
 * @returns {Promise<{ outcome: string; shop?: string | null; host?: string | null }>}
 */
export async function recoverEmbeddedAdminAuth(windowLike, options = {}) {
  const appPath = options.appPath ?? "/app";
  const timeoutMs = options.timeoutMs ?? 15000;
  const params = new URLSearchParams(windowLike.location.search);
  const shopParam = params.get("shop");
  const hostParam = params.get("host");

  if (shopParam && hostParam) {
    const target = new URL(appPath, windowLike.location.origin);
    for (const [key, value] of params.entries()) {
      target.searchParams.set(key, value);
    }
    if (!target.searchParams.get("embedded")) {
      target.searchParams.set("embedded", "1");
    }
    windowLike.location.assign(target.toString());
    return { outcome: "redirect_launch_params" };
  }

  const shopify = await waitForShopifyGlobal(windowLike, timeoutMs);
  if (!shopify) {
    return { outcome: "shopify_unavailable" };
  }

  if (shopify.ready && typeof shopify.ready.then === "function") {
    await shopify.ready;
  }

  const shop = String(shopify.config?.shop || "").trim();
  const host = String(shopify.config?.host || "").trim();
  if (!shop || !host) {
    return { outcome: "missing_config", shop: shop || null, host: host || null };
  }

  const bouncePath = buildSessionTokenBouncePath({
    shop,
    host,
    appPath,
    appOrigin: windowLike.location.origin,
  });
  windowLike.location.assign(bouncePath);
  return { outcome: "bounce", shop, host };
}
