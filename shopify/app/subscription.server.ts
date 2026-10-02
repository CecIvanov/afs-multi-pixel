import type { AdminApiContext } from "@shopify/shopify-app-react-router/server";
import { reconcileBilling } from "./backend.server";
import { billingMode } from "./billing.server";
import { logError, logInfo } from "./logger.server";
import { fetchPartnerSubscriptionSnapshot, fetchShopGid } from "./partner-billing.server";
import { honoursRedirectHint, shouldReuseCheck } from "./subscription.shared.mjs";

const CHECK_TTL_MS = 5 * 60 * 1000;

type CheckResult = { active: boolean };
const lastCheck = new Map<string, { at: number; result: CheckResult }>();
const inFlight = new Map<string, Promise<CheckResult>>();

/**
 * Does the shop have a plan (spec §5)? On app open the Partner API
 * activeSubscription is read and handed to the backend, which reconciles it the
 * way Shopify changes plans (upgrade at once; downgrade pending until the cycle
 * ends) and answers whether the effective plan gives access (any catalog plan
 * above "none"). `hint` is the plan_handle Shopify adds to the URL right after the
 * merchant picks a plan: it forces a fresh read and is honoured while the Partner
 * API catches up. Billing mode "disabled" (the UAT custom app) always has access,
 * and a failed read never locks a merchant out.
 */
export async function checkPlanSubscription(
  admin: AdminApiContext,
  shop: string,
  { hint = null, fresh = false }: { hint?: string | null; fresh?: boolean } = {},
): Promise<CheckResult> {
  if (billingMode() === "disabled") return { active: true };

  const forceFresh = fresh || Boolean(hint);
  const cached = lastCheck.get(shop);
  if (shouldReuseCheck({ cachedAt: cached?.at ?? null, now: Date.now(), ttlMs: CHECK_TTL_MS, forceFresh })) {
    return cached!.result;
  }
  const running = inFlight.get(shop);
  if (running) return running;

  const run = (async () => {
    try {
      const shopGid = await fetchShopGid(admin);
      const snapshot = await fetchPartnerSubscriptionSnapshot(shopGid);
      const reconciled = await reconcileBilling({
        shop_domain: shop,
        source: hint ? "redirect" : fresh ? "billing_page" : "app_load",
        partner_snapshot: snapshot,
        shop_gid: shopGid,
      });
      const result = { active: honoursRedirectHint(reconciled.subscribed, hint) };
      lastCheck.set(shop, { at: Date.now(), result });
      logInfo("billing.reconciled", {
        shop,
        action: reconciled.action,
        effective: reconciled.effective_plan_handle,
        pending: reconciled.pending_plan_handle,
        hint,
      });
      return result;
    } catch (error) {
      logError("subscription_check_failed", error, { shop });
      return { active: true };
    } finally {
      inFlight.delete(shop);
    }
  })();
  inFlight.set(shop, run);
  return run;
}
