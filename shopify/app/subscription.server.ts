import type { AdminApiContext } from "@shopify/shopify-app-react-router/server";
import { reconcileBilling } from "./backend.server";
import { billingMode } from "./billing.server";
import { logError, logInfo } from "./logger.server";
import { fetchPartnerSubscriptionSnapshot, fetchShopGid } from "./partner-billing.server";
import { returnedFromShopifyBilling, shouldReuseCheck } from "./subscription.shared.mjs";

const SYNC_TTL_MS = 5 * 60 * 1000;

type Hints = { planHandle: string | null; chargeId: string | null };

const lastSync = new Map<string, number>();
const inFlight = new Map<string, Promise<void>>();

/**
 * Sync the shop's plan with Shopify (spec §5), as BG Delivery does: the Partner
 * API activeSubscription and Shopify's redirect hints (?plan_handle, ?charge_id)
 * go to the backend, which stores the plan the way Shopify changes plans
 * (upgrade at once; downgrade pending until the cycle ends). The caller then
 * reads the stored plan. A failed sync is logged and leaves the stored plan as is.
 */
export async function syncPlanWithShopify(
  admin: AdminApiContext,
  shop: string,
  { hints, fresh = false }: { hints: Hints; fresh?: boolean },
): Promise<void> {
  if (billingMode() === "disabled") return;

  const returned = returnedFromShopifyBilling(hints);
  const forceFresh = fresh || returned;
  if (shouldReuseCheck({ cachedAt: lastSync.get(shop) ?? null, now: Date.now(), ttlMs: SYNC_TTL_MS, forceFresh })) {
    return;
  }
  const running = inFlight.get(shop);
  if (running) return running;

  const run = (async () => {
    try {
      const shopGid = await fetchShopGid(admin);
      const snapshot = await fetchPartnerSubscriptionSnapshot(shopGid);
      const reconciled = await reconcileBilling({
        shop_domain: shop,
        source: returned ? "redirect" : fresh ? "billing_page" : "app_load",
        partner_snapshot: snapshot,
        shop_gid: shopGid,
        redirect_hint: returned ? { plan_handle: hints.planHandle, charge_id: hints.chargeId } : undefined,
      });
      lastSync.set(shop, Date.now());
      logInfo("billing.reconciled", {
        shop,
        action: reconciled.action,
        effective: reconciled.effective_plan_handle,
        pending: reconciled.pending_plan_handle,
        planHandle: hints.planHandle,
        chargeId: hints.chargeId,
      });
    } catch (error) {
      logError("billing.reconcile_failed", error, { shop, planHandle: hints.planHandle, chargeId: hints.chargeId });
    } finally {
      inFlight.delete(shop);
    }
  })();
  inFlight.set(shop, run);
  return run;
}
