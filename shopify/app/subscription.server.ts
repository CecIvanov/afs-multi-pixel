import type { AdminApiContext } from "@shopify/shopify-app-react-router/server";
import { reconcileBilling } from "./backend.server";
import { billingMode } from "./billing.server";
import { logError, logInfo } from "./logger.server";
import {
  fetchActiveAppSubscriptions,
  fetchPartnerSubscriptionSnapshot,
  fetchShopGid,
  type PartnerSubscriptionSnapshot,
} from "./partner-billing.server";
import { returnedFromShopifyBilling, shouldReuseCheck, verifiedRedirectHint } from "./subscription.shared.mjs";

const SYNC_TTL_MS = 5 * 60 * 1000;

const NO_CONTRACT: PartnerSubscriptionSnapshot = {
  has_active_contract: false,
  effective_plan_handle: null,
  pending_plan_handle: null,
  billing_period: null,
  cancel_at_end_of_cycle: false,
  cycle_start: null,
  cycle_end: null,
  trial_ends_at: null,
};

type Hints = { planHandle: string | null; chargeId: string | null };

const lastSync = new Map<string, number>();
const inFlight = new Map<string, Promise<void>>();

/**
 * Sync the shop's plan with Shopify (spec §5), as BG Delivery does: the Partner
 * API activeSubscription and Shopify's redirect hints (?plan_handle, ?charge_id)
 * go to the backend, which stores the plan the way Shopify changes plans
 * (upgrade at once; downgrade pending until the cycle ends). The redirect hint
 * counts only when the Admin API shows that subscription ACTIVE, and it goes
 * through even when the Partner API read fails (so a merchant back from
 * Shopify's plan page isn't sent there again). A failed Partner API read never
 * downgrades. The caller then reads the stored plan.
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
      // Shopify's redirect, confirmed against the shop's active subscription.
      const redirectHint = returned
        ? verifiedRedirectHint(
            hints,
            await fetchActiveAppSubscriptions(admin).catch((error) => {
              logError("billing.active_subscriptions_failed", error, { shop });
              return [];
            }),
          )
        : null;
      let snapshot: PartnerSubscriptionSnapshot | null = null;
      try {
        snapshot = await fetchPartnerSubscriptionSnapshot(shopGid);
      } catch (error) {
        // A failed read is not "no subscription": never downgrade on it. The
        // confirmed redirect hint still goes through.
        logError("billing.partner_api_failed", error, { shop });
      }
      if (!snapshot && !redirectHint) return;
      const reconciled = await reconcileBilling({
        shop_domain: shop,
        source: returned ? "redirect" : fresh ? "billing_page" : "app_load",
        partner_snapshot: snapshot ?? NO_CONTRACT,
        shop_gid: shopGid,
        redirect_hint: redirectHint ?? undefined,
      });
      lastSync.set(shop, Date.now());
      logInfo("billing.reconciled", {
        shop,
        action: reconciled.action,
        effective: reconciled.effective_plan_handle,
        pending: reconciled.pending_plan_handle,
        planHandle: hints.planHandle,
        chargeId: hints.chargeId,
        hintConfirmed: Boolean(redirectHint),
        partnerApiRead: Boolean(snapshot),
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
