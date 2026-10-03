// Plan access (spec §1, §5), billed by Shopify App Pricing: on app open the
// shop's plan is read from the Partner API and stored by the backend; a shop
// without a stored plan is sent to Shopify's plan page until it has one, and
// Shopify sends the merchant back with ?plan_handle=… (and ?charge_id=…), which
// the backend stores while the Partner API catches up. Pure, so node --test covers it.

/** What Shopify adds to the app URL after the merchant picks a plan. */
export function billingRedirectHints(url) {
  return {
    planHandle: url.searchParams.get("plan_handle")?.trim().toLowerCase() || null,
    chargeId: url.searchParams.get("charge_id")?.trim() || null,
  };
}

/** Did Shopify just send the merchant back from its plan page? */
export function returnedFromShopifyBilling(hints) {
  return Boolean(hints.planHandle || hints.chargeId);
}

/**
 * Send the shop to Shopify's plan page? Whenever billing is on and no plan is
 * stored — again and again until one is. (A merchant back from that page with
 * ?plan_handle=… has it stored first, so they get in.)
 */
export function requiresPlanSelection({ billingEnabled, subscribed }) {
  return billingEnabled && !subscribed;
}

/**
 * Is this the admin loading the app's page itself (?embedded=1)? Only then can
 * the server redirect to Shopify's plan page; an in-app navigation is a data
 * request, where Shopify's redirect() answers a bare 401 — so the page opens
 * the plan page with App Bridge instead.
 */
export function isFullPageLoad(url) {
  return url.searchParams.get("embedded") === "1";
}

/**
 * The redirect hint, only when Shopify confirms it: the shop must have an ACTIVE
 * app subscription (Admin API currentAppInstallation.activeSubscriptions, which
 * shows it at once), and a ?charge_id must be that subscription's ID. A hand-made
 * or replayed ?plan_handle=… (after a cancel) is dropped.
 *
 * @param {{ planHandle: string | null, chargeId: string | null }} hints
 * @param {{ id?: string | null, status?: string | null }[]} activeSubscriptions
 * @returns {{ plan_handle: string, charge_id: string | null } | null}
 */
export function verifiedRedirectHint(hints, activeSubscriptions) {
  if (!hints.planHandle) return null;
  const active = (activeSubscriptions || []).filter((s) => String(s.status || "").toUpperCase() === "ACTIVE");
  if (!active.length) return null;
  if (hints.chargeId && !active.some((s) => String(s.id || "").split("/").pop() === hints.chargeId)) return null;
  return { plan_handle: hints.planHandle, charge_id: hints.chargeId };
}

/** The Partner API is slow and rate-limited: reuse a recent answer, except right
 * after a billing redirect or on the Plan page. */
export function shouldReuseCheck({ cachedAt, now, ttlMs, forceFresh }) {
  return !forceFresh && cachedAt != null && now - cachedAt < ttlMs;
}
