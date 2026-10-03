import type { LoaderFunctionArgs } from "react-router";
import { useLoaderData } from "react-router";
import { authenticate } from "../shopify.server";
import { managedPricingPlansUrl, resolveAppHandle } from "../billing.server";
import { isFullPageLoad } from "../subscription.shared.mjs";
import { GoToShopifyPlans } from "../components/go-to-shopify-plans";

// The Plan page (spec §1, §5) is Shopify's own plan page: plans are chosen,
// changed and cancelled there, so this route always sends the merchant to it —
// a server redirect on a full page load, App Bridge on an in-app navigation
// (where a server redirect would answer 401).
export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { session, redirect } = await authenticate.admin(request);
  if (!resolveAppHandle()) throw redirect("/app");
  const plansUrl = managedPricingPlansUrl(session.shop);
  if (isFullPageLoad(new URL(request.url))) throw redirect(plansUrl, { target: "_top" });
  return { plansUrl };
};

export default function Plan() {
  const { plansUrl } = useLoaderData<typeof loader>();
  return <GoToShopifyPlans url={plansUrl} />;
}
