import type { ActionFunctionArgs } from "react-router";
import { ingestShopifyWebhook } from "./backend.server";
import { logError, logInfo } from "./logger.server";
import { withRequestContext } from "./request-context.server";
import { receiveWebhook } from "./webhook-ingest.shared.mjs";

/** The action of every webhook route: verify the HMAC, store the webhook, answer
 *  200. The backend worker does the handler work (backend/app/services/job_processors.py). */
export const webhookAction = ({ request }: ActionFunctionArgs) =>
  receiveWebhook(request, {
    apiSecretKey: process.env.SHOPIFY_API_SECRET || "",
    ingest: ingestShopifyWebhook,
    withContext: withRequestContext,
    logInfo,
    logError,
  });
