import { useRouteLoaderData } from "react-router";
import type { LoaderFunctionArgs } from "react-router";
import { useLoaderData } from "react-router";
import { authenticate } from "../shopify.server";
import { managedPricingPlansUrl, resolveAppHandle, usesManagedPricing } from "../billing.server";

// The plan page (spec §1, §5): one paid plan, chosen on Shopify's own pricing page.
// Shops without an active subscription are sent here and see nothing else.
export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { session } = await authenticate.admin(request);
  const managed = usesManagedPricing() && Boolean(resolveAppHandle());
  return { plansUrl: managed ? managedPricingPlansUrl(session.shop) : null };
};

export default function Plan() {
  const { plansUrl } = useLoaderData<typeof loader>();
  const app = useRouteLoaderData("routes/app") as { subscribed?: boolean; planHandle?: string | null } | undefined;
  const subscribed = app?.subscribed ?? false;

  return (
    <s-page heading="Plan">
      <s-section heading={subscribed ? "Your plan is active" : "Choose your plan"}>
        {subscribed ? (
          <s-paragraph>
            Every Market can have its own Meta pixel, with browser and server events. Shopify bills the plan; manage
            or cancel it on Shopify's plan page.
          </s-paragraph>
        ) : (
          <s-stack gap="base">
            <s-banner tone="warning" heading="No active plan">
              AFS Multi Pixel sends no events until you choose the plan. Your Markets and pixels are kept.
            </s-banner>
            <s-paragraph>The plan includes per-Market pixels, browser and server events, and the event log.</s-paragraph>
          </s-stack>
        )}
        {plansUrl ? (
          <s-button variant={subscribed ? "secondary" : "primary"} href={plansUrl} target="_top">
            {subscribed ? "Manage plan" : "Choose plan"}
          </s-button>
        ) : null}
      </s-section>
    </s-page>
  );
}
