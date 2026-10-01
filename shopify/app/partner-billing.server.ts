// Partner API `activeSubscription` snapshot — the source of truth under managed
// pricing. This is a THIN adapter over the Partner API and needs
// SHOPIFY_APP_GID + SHOPIFY_PARTNER_ORG_ID + SHOPIFY_PARTNER_ACCESS_TOKEN
// (Partner API 2026-07+). It cannot be unit-tested (network); the backend
// reconcile STATE MACHINE takes a snapshot, so its logic is fully tested.

export type PartnerSubscriptionSnapshot = {
  has_active_contract: boolean;
  effective_plan_handle: string | null;
  pending_plan_handle: string | null;
  billing_period: "monthly" | "yearly" | null;
  cancel_at_end_of_cycle: boolean;
  cycle_start: string | null;
  cycle_end: string | null;
  legacy_subscription_id: string | null;
  trial_ends_at: string | null;
};

export function partnerApiConfigured(): boolean {
  return Boolean(
    process.env.SHOPIFY_APP_GID &&
      process.env.SHOPIFY_PARTNER_ORG_ID &&
      process.env.SHOPIFY_PARTNER_ACCESS_TOKEN,
  );
}

/** A safe "no active contract" snapshot — reconcile treats it as free/cancelled. */
export function emptySnapshot(): PartnerSubscriptionSnapshot {
  return {
    has_active_contract: false,
    effective_plan_handle: null,
    pending_plan_handle: null,
    billing_period: null,
    cancel_at_end_of_cycle: false,
    cycle_start: null,
    cycle_end: null,
    legacy_subscription_id: null,
    trial_ends_at: null,
  };
}

/**
 * Fetch the store's active subscription snapshot from the Partner API. Returns
 * an empty snapshot when the Partner API isn't configured so the app runs
 * without billing credentials in development. Implement the real query for prod.
 */
export async function fetchActiveSubscription(_shop: string): Promise<PartnerSubscriptionSnapshot> {
  if (!partnerApiConfigured()) {
    return emptySnapshot();
  }
  // TODO: query the Partner API `app { ... activeSubscription }` and map it here.
  return emptySnapshot();
}
