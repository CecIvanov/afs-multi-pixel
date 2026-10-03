import type { LoaderFunctionArgs } from "react-router";
import { authenticate } from "../shopify.server";
import { managedPricingPlansUrl, resolveAppHandle } from "../billing.server";

// The Plan page (spec §1, §5) is Shopify's own plan page: plans are chosen,
// changed and cancelled there, so this route always sends the merchant to it.
// (The app shell syncs the plan with Shopify before this loader runs.)
export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { session, redirect } = await authenticate.admin(request);
  if (!resolveAppHandle()) throw redirect("/app");
  throw redirect(managedPricingPlansUrl(session.shop), { target: "_top" });
};

export default function Plan() {
  return null;
}
