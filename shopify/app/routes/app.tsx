import type { HeadersFunction, LoaderFunctionArgs } from "react-router";
import { Link, Outlet, useLoaderData, useRouteError } from "react-router";
import { boundary } from "@shopify/shopify-app-react-router/server";
import { AppProvider } from "@shopify/shopify-app-react-router/react";
import { NavMenu } from "@shopify/app-bridge-react";

import { authenticate } from "../shopify.server";
import { ensureBackendTenant } from "../tenant.server";
import { checkPlanSubscription } from "../subscription.server";
import { planHandleHint } from "../subscription.shared.mjs";
import { billingMode } from "../billing.server";
import { fetchBillingByShop } from "../backend.server";
import { resolveSupportConfig } from "../support.server";
import { ViberFab } from "../components/viber-fab";
import { withRequestContext } from "../request-context.server";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { session, admin, redirect } = await authenticate.admin(request);
  return withRequestContext(request, session.shop, async () => {
    // Keep the backend tenant + its Shopify token fresh on every navigation.
    try {
      await ensureBackendTenant(session);
    } catch {
      // Token sync must never block the embedded admin from loading.
    }
    // Plans (spec §5): without one the admin shows only the Plan page. Shopify's
    // redirect after plan selection carries ?plan_handle=…, which forces a fresh
    // check.
    const url = new URL(request.url);
    const billingEnabled = billingMode() !== "disabled";
    const onPlanPage = url.pathname === "/app/billing";
    // A custom app (UAT) has no billing: there's no Plan page to show.
    if (!billingEnabled && onPlanPage) throw redirect("/app");
    const subscription = await checkPlanSubscription(admin, session.shop, {
      hint: planHandleHint(url),
      fresh: onPlanPage,
    });
    if (!subscription.active && !onPlanPage) {
      throw redirect("/app/billing");
    }
    // The effective plan, and a downgrade waiting for the end of the cycle.
    const plan = billingEnabled ? await fetchBillingByShop(session.shop).catch(() => null) : null;
    const support = resolveSupportConfig();
    return {
      apiKey: process.env.SHOPIFY_API_KEY || "",
      plan: plan?.subscribed
        ? {
            name: plan.plan_name,
            pendingName: plan.pending_plan_name,
            changesOn: plan.pending_plan_handle ? plan.current_period_end : null,
          }
        : null,
      billingEnabled,
      subscribed: subscription.active,
      viber: support.viber, // { enabled, numberE164, label }
    };
  });
};

export default function App() {
  const { apiKey, viber, billingEnabled } = useLoaderData<typeof loader>();
  return (
    <AppProvider apiKey={apiKey}>
      <NavMenu>
        <Link to="/app" rel="home">Markets</Link>
        {billingEnabled ? <Link to="/app/billing">Plan</Link> : null}
        <Link to="/app/settings">Settings</Link>
        <Link to="/app/help">Help</Link>
      </NavMenu>
      <Outlet />
      {/* Configurable via app.config.json support.viber.enabled — renders only when on. */}
      <ViberFab enabled={viber.enabled} numberE164={viber.numberE164} label={viber.label} />
    </AppProvider>
  );
}

// Contextual error boundary + CSP headers so errors/embeds don't dead-end.
export function ErrorBoundary() {
  return boundary.error(useRouteError());
}

export const headers: HeadersFunction = (headersArgs) => boundary.headers(headersArgs);
