import type { ActionFunctionArgs } from "react-router";
import { authenticate } from "../shopify.server";
import { ingestShopifyWebhook } from "../backend.server";
import prisma from "../db.server";
import { logError, logInfo } from "../logger.server";
import { withRequestContext } from "../request-context.server";

export const action = async ({ request }: ActionFunctionArgs) => {
  const { shop, topic } = await authenticate.webhook(request);
  const webhookId = request.headers.get("X-Shopify-Webhook-Id");

  return withRequestContext(request, shop, async () => {
    logInfo("shopify.webhook.received", { topic });
    try {
      // Backend: enqueue the SOFT uninstall job (keeps row + data, drops token).
      await ingestShopifyWebhook({ shop, topic, webhookId });
      // Node: delete the local OAuth sessions for this shop.
      await prisma.session.deleteMany({ where: { shop } });
      logInfo("shopify.webhook.app_uninstalled.done", { shop });
    } catch (error) {
      logError("shopify.webhook.app_uninstalled.failed", error, { shop });
      return new Response("Webhook ingest failed", { status: 500 });
    }
    return new Response();
  });
};
