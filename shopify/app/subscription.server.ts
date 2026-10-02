import type { AdminApiContext } from "@shopify/shopify-app-react-router/server";
import { reportSubscription } from "./backend.server";
import { billingMode } from "./billing.server";
import { logError, logInfo } from "./logger.server";
import { fetchPartnerSubscriptionSnapshot, fetchShopGid } from "./partner-billing.server";
import { isSubscribed, shouldReuseCheck } from "./subscription.shared.mjs";

const CHECK_TTL_MS = 5 * 60 * 1000;

/** The one paid plan's exact handle in Shopify App Pricing (spec §5). */
export function planHandle(): string {
  return (process.env.BILLING_PLAN_HANDLE || "light").trim().toLowerCase();
}

type CheckResult = { active: boolean; planHandle: string };
const lastCheck = new Map<string, { at: number; result: CheckResult }>();
const inFlight = new Map<string, Promise<CheckResult>>();

/**
 * Is the shop subscribed to the one plan? Read from the Partner API on app open
 * and reported to the backend, which stops Relays without it. `hint` is the
 * plan_handle Shopify adds to the URL right after the merchant picks a plan: it
 * forces a fresh read and is honoured while the Partner API catches up. Billing
 * mode "disabled" (the UAT App's custom distribution can't charge) counts as
 * subscribed, and a failed read never locks a merchant out.
 */
export async function checkPlanSubscription(
  admin: AdminApiContext,
  shop: string,
  { hint = null, fresh = false }: { hint?: string | null; fresh?: boolean } = {},
): Promise<CheckResult> {
  const handle = planHandle();
  if (billingMode() === "disabled") return { active: true, planHandle: handle };

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
      const active = isSubscribed(snapshot, handle) || hint === handle;
      const result = { active, planHandle: handle };
      lastCheck.set(shop, { at: Date.now(), result });
      logInfo("billing.subscription_checked", { shop, active, planHandle: snapshot.effective_plan_handle, hint });
      await reportSubscription(shop, active, shopGid).catch((error) =>
        logError("subscription_report_failed", error, { shop }),
      );
      return result;
    } catch (error) {
      logError("subscription_check_failed", error, { shop });
      return { active: true, planHandle: handle };
    } finally {
      inFlight.delete(shop);
    }
  })();
  inFlight.set(shop, run);
  return run;
}
