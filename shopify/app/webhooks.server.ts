import type { ActionFunctionArgs } from "react-router";
import { ingestShopifyWebhook } from "./backend.server";
import { logError, logInfo } from "./logger.server";
import { withRequestContext } from "./request-context.server";
import { authenticate } from "./shopify.server";
import { receiveWebhook } from "./webhook-ingest.shared.mjs";

/** The action of every inbox webhook route: verify, store, answer. The backend
 *  worker does the handler work (see backend/app/services/job_processors.py). */
export const webhookAction = ({ request }: ActionFunctionArgs) =>
  receiveWebhook(request, {
    authenticate: authenticate.webhook,
    ingest: ingestShopifyWebhook,
    withContext: withRequestContext,
    logInfo,
    logError,
  });
