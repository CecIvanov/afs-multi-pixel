import type { LoaderFunctionArgs } from "react-router";
import { authenticate } from "../shopify.server";
import { listEvents } from "../backend.server";
import { withRequestContext } from "../request-context.server";

// The event log's data (spec §4), loaded by the Markets page's drawer.
export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { session } = await authenticate.admin(request);
  const market = Number(new URL(request.url).searchParams.get("market")) || undefined;
  return withRequestContext(request, session.shop, () => listEvents(session.shop, market));
};
