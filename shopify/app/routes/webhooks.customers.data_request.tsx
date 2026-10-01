import type { ActionFunctionArgs } from "react-router";
import { authenticate } from "../shopify.server";
import { ingestShopifyWebhook } from "../backend.server";
import { logError, logInfo } from "../logger.server";
import { withRequestContext } from "../request-context.server";

// Mandatory GDPR compliance webhook. HMAC-verified, enqueues a durable job, acks fast.
export const action = async ({ request }: ActionFunctionArgs) => {
  const { payload, shop, topic } = await authenticate.webhook(request);
  const webhookId = request.headers.get("X-Shopify-Webhook-Id");
  return withRequestContext(request, shop, async () => {
    logInfo("shopify.webhook.compliance.received", { topic, shop });
    try {
      await ingestShopifyWebhook({ shop, topic, webhookId, payload: payload as Record<string, unknown> });
    } catch (error) {
      logError("shopify.webhook.compliance.failed", error, { shop, topic });
      return new Response("Webhook ingest failed", { status: 500 });
    }
    return new Response();
  });
};
