import type { ActionFunctionArgs } from "react-router";
import { authenticate } from "../shopify.server";
import { reconcileBillingOnLoad } from "../billing-reconcile.server";
import { logInfo } from "../logger.server";
import { withRequestContext } from "../request-context.server";

// app_subscriptions/update. Under managed pricing this is NOT the source of truth
// (the Partner API is) — so we just log it and kick a reconcile, then ack.
export const action = async ({ request }: ActionFunctionArgs) => {
  const { shop, topic } = await authenticate.webhook(request);
  return withRequestContext(request, shop, async () => {
    logInfo("shopify.webhook.subscriptions_update", { topic, shop });
    await reconcileBillingOnLoad(shop, "app_load");
    return new Response();
  });
};
