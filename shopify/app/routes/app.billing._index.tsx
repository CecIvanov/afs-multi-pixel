import { useRouteLoaderData } from "react-router";
import type { LoaderFunctionArgs } from "react-router";
import { useLoaderData } from "react-router";
import { authenticate } from "../shopify.server";
import { managedPricingPlansUrl, resolveAppHandle, usesManagedPricing } from "../billing.server";

// The Plan page (spec §1, §5): plans are chosen and changed on Shopify's own
// pricing page. Shops without a plan are sent here and see nothing else. A
// downgrade stays pending until the end of the cycle, as Shopify does it.
export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { session } = await authenticate.admin(request);
  const managed = usesManagedPricing() && Boolean(resolveAppHandle());
  return { plansUrl: managed ? managedPricingPlansUrl(session.shop) : null };
};

type AppData = {
  plan?: { name: string; pendingName: string | null; changesOn: string | null } | null;
};

const DATE = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric" });

export default function Plan() {
  const { plansUrl } = useLoaderData<typeof loader>();
  const plan = (useRouteLoaderData("routes/app") as AppData | undefined)?.plan ?? null;

  return (
    <s-page heading="Plan">
      <s-section heading={plan ? `${plan.name} plan` : "Choose your plan"}>
        {plan ? (
          <s-stack gap="base">
            <s-paragraph>
              Every Market can have its own Meta pixel, with browser and server events. Shopify bills the plan;
              change or cancel it on Shopify's plan page.
            </s-paragraph>
            {plan.pendingName && plan.changesOn ? (
              <s-banner tone="info" heading={`Changing to ${plan.pendingName}`}>
                {plan.name} stays active until {DATE.format(new Date(plan.changesOn))}, the end of this billing cycle.
                Then the {plan.pendingName} plan starts.
              </s-banner>
            ) : null}
          </s-stack>
        ) : (
          <s-stack gap="base">
            <s-banner tone="warning" heading="No plan">
              AFS Multi Pixel sends no events until you choose a plan. Your Markets and pixels are kept.
            </s-banner>
            <s-paragraph>Plans include per-Market pixels, browser and server events, and the event log.</s-paragraph>
          </s-stack>
        )}
        {plansUrl ? (
          <s-button variant={plan ? "secondary" : "primary"} href={plansUrl} target="_top">
            {plan ? "Change plan" : "Choose plan"}
          </s-button>
        ) : null}
      </s-section>
    </s-page>
  );
}
