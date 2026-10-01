// Reconcile the tenant's subscription on app load: fetch the Partner-API snapshot
// and hand it to the backend state machine. In-flight-deduped per shop so a burst
// of navigations doesn't reconcile repeatedly.

import { reconcileBilling } from "./backend.server";
import { fetchActiveSubscription } from "./partner-billing.server";
import { usesManagedPricing } from "./billing.server";
import { logError } from "./logger.server";

const inFlight = new Map<string, Promise<void>>();

export async function reconcileBillingOnLoad(shop: string, source = "app_load"): Promise<void> {
  if (!usesManagedPricing()) return;
  const existing = inFlight.get(shop);
  if (existing) return existing;

  const promise = (async () => {
    try {
      const snapshot = await fetchActiveSubscription(shop);
      await reconcileBilling({ shop_domain: shop, source, partner_snapshot: snapshot });
    } catch (error) {
      // Billing reconcile must never block the embedded admin from loading.
      logError("billing_reconcile_failed", error, { shop });
    }
  })().finally(() => inFlight.delete(shop));

  inFlight.set(shop, promise);
  return promise;
}
