// The one paid plan (spec §1, §5), billed by Shopify App Pricing. The app knows
// only the plan's exact handle and reads the shop's subscription from the Partner
// API. Pure, so node --test covers it.

/**
 * @param {{ has_active_contract: boolean, effective_plan_handle: string | null } | null | undefined} snapshot
 * @param {string} planHandle
 */
export function isSubscribed(snapshot, planHandle) {
  return Boolean(
    snapshot?.has_active_contract &&
      String(snapshot.effective_plan_handle ?? "").toLowerCase() === planHandle.toLowerCase(),
  );
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
