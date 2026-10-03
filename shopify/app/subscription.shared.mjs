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

/** The Partner API is slow and rate-limited: reuse a recent answer, except right
 * after a billing redirect or on the Plan page. */
export function shouldReuseCheck({ cachedAt, now, ttlMs, forceFresh }) {
  return !forceFresh && cachedAt != null && now - cachedAt < ttlMs;
}
