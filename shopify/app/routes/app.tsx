import type { HeadersFunction, LoaderFunctionArgs } from "react-router";
import { Link, Outlet, useLoaderData, useRouteError } from "react-router";
import { boundary } from "@shopify/shopify-app-react-router/server";
import { AppProvider } from "@shopify/shopify-app-react-router/react";
import { NavMenu } from "@shopify/app-bridge-react";

import { authenticate } from "../shopify.server";
import { ensureBackendTenant } from "../tenant.server";
import { checkPlanSubscription } from "../subscription.server";
import { planHandleHint } from "../subscription.shared.mjs";
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
    // The one paid plan (spec §5): without an active subscription the admin
    // shows only the plan page. Shopify's redirect after plan selection carries
    // ?plan_handle=…, which forces a fresh check.
    const url = new URL(request.url);
    const onPlanPage = url.pathname === "/app/billing";
    const subscription = await checkPlanSubscription(admin, session.shop, {
      hint: planHandleHint(url),
      fresh: onPlanPage,
    });
    if (!subscription.active && !onPlanPage) {
      throw redirect("/app/billing");
    }
    const support = resolveSupportConfig();
    return {
      apiKey: process.env.SHOPIFY_API_KEY || "",
      planHandle: subscription.active ? subscription.planHandle : null,
      subscribed: subscription.active,
      viber: support.viber, // { enabled, numberE164, label }
    };
  });
};

export default function App() {
  const { apiKey, viber } = useLoaderData<typeof loader>();
  return (
    <AppProvider apiKey={apiKey}>
      <NavMenu>
        <Link to="/app" rel="home">Markets</Link>
        <Link to="/app/billing">Plan</Link>
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
