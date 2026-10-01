import type { AdminApiContext } from "@shopify/shopify-app-react-router/server";
import { reportSubscription } from "./backend.server";
import { billingMode } from "./billing.server";
import { logError } from "./logger.server";
import { hasActivePlan } from "./subscription.shared.mjs";

/** The exact plan name from the Partner Dashboard (managed pricing). */
export function planName(): string {
  return process.env.BILLING_PLAN_NAME || "AFS Multi Pixel";
}

/**
 * Is the shop subscribed to the one plan? Read from the Admin API on app open and
 * reported to the backend, which stops Relays without it. Billing mode "disabled"
 * (the UAT App's custom distribution can't charge) counts as subscribed.
 */
export async function checkPlanSubscription(admin: AdminApiContext, shop: string) {
  if (billingMode() === "disabled") return { active: true, planName: planName() };
  let active = false;
  try {
    const response = await admin.graphql(
      `#graphql
        query MultiPixelSubscription {
          currentAppInstallation { activeSubscriptions { name status } }
        }`,
    );
    const json = await response.json();
    active = hasActivePlan(json.data?.currentAppInstallation?.activeSubscriptions, planName());
  } catch (error) {
    // Don't lock a paying merchant out on a transient Shopify error.
    logError("subscription_check_failed", error, { shop });
    return { active: true, planName: planName() };
  }
  try {
    await reportSubscription(shop, active);
  } catch (error) {
    logError("subscription_report_failed", error, { shop });
  }
  return { active, planName: planName() };
}
