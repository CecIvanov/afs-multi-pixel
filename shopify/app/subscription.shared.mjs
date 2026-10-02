// Plan access (spec §1, §5), billed by Shopify App Pricing: the shop's plan is read
// from the Partner API and reconciled in the backend. Pure, so node --test covers it.

/**
 * Right after the merchant picks a plan, Shopify's redirect names it; the Partner
 * API may not show it yet, so the redirect alone lets the merchant in this once.
 * @param {boolean} subscribed  what the backend reconciled
 * @param {string | null} hint  ?plan_handle=… from the redirect
 */
export function honoursRedirectHint(subscribed, hint) {
  return subscribed || Boolean(hint && hint !== "none");
}

/** Shopify redirects back with ?plan_handle=… once the merchant picks a plan. */
export function planHandleHint(url) {
  return url.searchParams.get("plan_handle")?.trim().toLowerCase() || null;
}

/** The Partner API is slow and rate-limited: reuse a recent answer, except right
 * after a billing redirect or on the Plan page. */
export function shouldReuseCheck({ cachedAt, now, ttlMs, forceFresh }) {
  return !forceFresh && cachedAt != null && now - cachedAt < ttlMs;
}
