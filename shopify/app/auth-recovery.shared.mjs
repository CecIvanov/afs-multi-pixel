/**
 * Embedded-admin auth recovery.
 *
 * When `@shopify/shopify-app-react-router` receives a document request to an
 * `/app/*` route with no session-token header and no `shop`/`host` launch
 * params, it redirects to the manual shop-domain login form (`/auth/login`).
 * Inside the Shopify admin this must never be shown to a merchant — it happens
 * after a deploy (a hard reload to a param-less URL) or any bare navigation.
 *
 * The correct recovery is to load App Bridge on the fallback page so it can
 * re-embed / re-authenticate the app automatically. This module contains the
 * pure decision logic so it can be unit tested without a running server.
 */

/** @typedef {"redirect" | "app-bridge" | "form"} AuthRecoveryKind */

/**
 * Distribution modes where the app is only ever used embedded inside the
 * Shopify admin. For these the shop-domain login form is never a valid thing to
 * render — we always re-embed via App Bridge instead.
 */
function isEmbeddedOnlyDistribution(distribution) {
  const normalized = String(distribution || "")
    .trim()
    .toLowerCase()
    .replace(/-/g, "_");
  return (
    normalized === "single_merchant" ||
    normalized === "singlemerchant" ||
    normalized === "shopify_admin" ||
    normalized === "shopifyadmin"
  );
}

/**
 * Shopify launch params that indicate the request already carries enough
 * context to hand back to the normal `/app` auth flow (which will bounce for a
 * fresh session token when needed).
 */
const LAUNCH_PARAM_KEYS = ["shop", "host", "embedded", "id_token", "session"];

function readHeader(headers, name) {
  if (!headers) return null;
  if (typeof headers.get === "function") {
    return headers.get(name);
  }
  const lower = name.toLowerCase();
  for (const key of Object.keys(headers)) {
    if (key.toLowerCase() === lower) {
      return headers[key];
    }
  }
  return null;
}

/**
 * Detect whether the request is being rendered inside an iframe (i.e. inside
 * the Shopify admin), even when the launch params are missing. `Sec-Fetch-Dest`
 * is the strongest signal; the referer is a fallback for older browsers.
 */
function isFramedRequest(headers) {
  const dest = String(readHeader(headers, "sec-fetch-dest") || "").toLowerCase();
  if (dest === "iframe" || dest === "nested-document") {
    return true;
  }
  const referer = String(readHeader(headers, "referer") || "");
  if (!referer) return false;
  try {
    const host = new URL(referer).hostname.toLowerCase();
    return (
      host === "admin.shopify.com" ||
      host.endsWith(".myshopify.com") ||
      host.endsWith(".shopify.com")
    );
  } catch {
    return false;
  }
}

function hasBearerToken(headers) {
  const authorization = readHeader(headers, "authorization");
  return Boolean(authorization && String(authorization).startsWith("Bearer "));
}

/**
 * @param {object} input
 * @param {string} [input.search] Raw `location.search` including leading `?`.
 * @param {Headers | Record<string, string>} [input.headers] Request headers.
 * @param {string} [input.distribution] `SHOPIFY_APP_DISTRIBUTION` value.
 * @param {string} [input.appPath] Target app path to redirect into (default `/app`).
 * @returns {{ kind: AuthRecoveryKind, to?: string, signals: Record<string, boolean> }}
 */
export function resolveEmbeddedAuthRecovery({
  search = "",
  headers,
  distribution,
  appPath = "/app",
} = {}) {
  const params = new URLSearchParams(search || "");
  const hasLaunchParams = LAUNCH_PARAM_KEYS.some((key) => Boolean(params.get(key)));
  const bearer = hasBearerToken(headers);
  const embeddedOnly = isEmbeddedOnlyDistribution(distribution);
  const framed = isFramedRequest(headers);

  const signals = {
    hasLaunchParams,
    bearer,
    embeddedOnly,
    framed,
  };

  if (hasLaunchParams || bearer) {
    const query = params.toString();
    return { kind: "redirect", to: query ? `${appPath}?${query}` : appPath, signals };
  }

  if (embeddedOnly || framed) {
    return { kind: "app-bridge", signals };
  }

  return { kind: "form", signals };
}

/**
 * Build the `/auth/session-token` bounce URL used by Shopify App Bridge to mint
 * an `id_token` and reload the embedded app document.
 *
 * @param {{
 *   shop: string;
 *   host: string;
 *   appPath?: string;
 *   appOrigin: string;
 *   sessionTokenPath?: string;
 * }} input
 */
export function buildSessionTokenBouncePath({
  shop,
  host,
  appPath = "/app",
  appOrigin,
  sessionTokenPath = "/auth/session-token",
}) {
  const reloadParams = new URLSearchParams({
    shop,
    host,
    embedded: "1",
  });
  const reloadTarget = `${appOrigin}${appPath}?${reloadParams.toString()}`;
  const bounceParams = new URLSearchParams({
    shop,
    host,
    embedded: "1",
    "shopify-reload": reloadTarget,
  });
  return `${sessionTokenPath}?${bounceParams.toString()}`;
}
