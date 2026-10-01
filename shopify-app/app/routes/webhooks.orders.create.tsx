import type { ActionFunctionArgs } from "react-router";
import { authenticate } from "../shopify.server";
import { handleOrderCreated } from "../models/relay.server";

// The server half of a Purchase: customer data for the CAPI event. authenticate.webhook verifies
// Shopify's HMAC; the Purchase is only sent once the browser half (consent + Market) has arrived.
export const action = async ({ request }: ActionFunctionArgs) => {
  const { shop, payload } = await authenticate.webhook(request);
  await handleOrderCreated(shop, payload as Record<string, unknown>);
  return new Response();
};
