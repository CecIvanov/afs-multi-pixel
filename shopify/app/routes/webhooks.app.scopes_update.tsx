import type { ActionFunctionArgs } from "react-router";
import { authenticate } from "../shopify.server";
import { ingestShopifyWebhook } from "../backend.server";
import { logError, logInfo } from "../logger.server";
import { withRequestContext } from "../request-context.server";

export const action = async ({ request }: ActionFunctionArgs) => {
  const { payload, session, topic, shop } = await authenticate.webhook(request);
  const webhookId = request.headers.get("X-Shopify-Webhook-Id");

  return withRequestContext(request, shop, async () => {
    logInfo("shopify.webhook.received", { topic });
    const scopes = ((payload.current as string[]) || []).join(",");
    // Pass the session token + new scopes so the job can persist them on the tenant.
    const webhookContext = session?.accessToken
      ? {
          access_token: session.accessToken,
          scopes,
          refresh_token: session.refreshToken ?? undefined,
          access_token_expires_at: session.expires?.toISOString(),
          refresh_token_expires_at: session.refreshTokenExpires?.toISOString(),
        }
      : undefined;
    try {
      await ingestShopifyWebhook({ shop, topic, webhookId, payload: payload as Record<string, unknown>, webhookContext });
    } catch (error) {
      logError("shopify.webhook.scopes_update.failed", error, { shop });
      return new Response("Webhook ingest failed", { status: 500 });
    }
    return new Response();
  });
};
