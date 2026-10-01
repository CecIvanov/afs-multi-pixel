import type { LoaderFunctionArgs } from "react-router";
import { useLoaderData } from "react-router";
import { authenticate } from "../shopify.server";
import { fetchBillingByShop } from "../backend.server";
import { managedPricingPlansUrl, resolveAppHandle, usesManagedPricing } from "../billing.server";
import { withRequestContext } from "../request-context.server";
import { logError } from "../logger.server";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { session } = await authenticate.admin(request);
  return withRequestContext(request, session.shop, async () => {
    let billing = null;
    try {
      billing = await fetchBillingByShop(session.shop);
    } catch (error) {
      logError("billing_page_fetch_failed", error, { shop: session.shop });
    }
    const managed = usesManagedPricing() && Boolean(resolveAppHandle());
    return {
      billing,
      plansUrl: managed ? managedPricingPlansUrl(session.shop) : null,
    };
  });
};

export default function Billing() {
  const { billing, plansUrl } = useLoaderData<typeof loader>();
  return (
    <s-page heading="Billing">
      <s-section heading="Your plan">
        {billing ? (
          <>
            <s-paragraph>
              Current plan: <s-badge tone="info">{billing.plan_name}</s-badge>
            </s-paragraph>
            {billing.pending_plan_handle ? (
              <s-banner tone="warning" heading="Scheduled change">
                Switching to {billing.pending_plan_handle} at the end of the current cycle.
              </s-banner>
            ) : null}
            <s-paragraph>
              Usage this period: {billing.used}
              {billing.quota != null ? ` / ${billing.quota}` : " (unlimited)"}
            </s-paragraph>
          </>
        ) : (
          <s-banner tone="warning" heading="Billing unavailable">
            Could not load billing right now — try again shortly.
          </s-banner>
        )}
        {plansUrl ? (
          <s-button href={plansUrl} target="_top">Choose a plan</s-button>
        ) : null}
      </s-section>
    </s-page>
  );
}
