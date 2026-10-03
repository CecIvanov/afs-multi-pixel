import type { HeadersFunction, LoaderFunctionArgs } from "react-router";
import { Link, Outlet, useLoaderData, useLocation, useRouteError } from "react-router";
import { GoToShopifyPlans } from "../components/go-to-shopify-plans";
import { boundary } from "@shopify/shopify-app-react-router/server";
import { AppProvider } from "@shopify/shopify-app-react-router/react";
import { NavMenu } from "@shopify/app-bridge-react";

import { authenticate } from "../shopify.server";
import { ensureBackendTenant } from "../tenant.server";
import { syncPlanWithShopify } from "../subscription.server";
import { billingRedirectHints, isFullPageLoad, requiresPlanSelection } from "../subscription.shared.mjs";
import { billingMode, managedPricingPlansUrl, resolveAppHandle } from "../billing.server";
import { fetchBillingByShop, listMarkets } from "../backend.server";
import { heldEventAlerts, marketTileState } from "../markets.shared.mjs";
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
    // Plans (spec §5): the plan chosen at install (or on Shopify's plan page) is
    // synced from Shopify and stored, including the ?plan_handle=… Shopify adds
    // when it sends the merchant back. Until a plan is stored, every app open goes
    // to Shopify's plan page (the Plan page route always goes there itself).
    const url = new URL(request.url);
    const billingEnabled = billingMode() !== "disabled";
    const onPlanPage = url.pathname === "/app/billing";
    // A custom app (UAT) has no billing: there's no Plan page to show.
    if (!billingEnabled && onPlanPage) throw redirect("/app");
    const hints = billingRedirectHints(url);
    if (billingEnabled) await syncPlanWithShopify(admin, session.shop, { hints, fresh: onPlanPage });
    // The effective plan, and a downgrade waiting for the end of the cycle.
    const plan = billingEnabled ? await fetchBillingByShop(session.shop).catch(() => null) : null;
    const subscribed = Boolean(plan?.subscribed);
    const plansUrl = billingEnabled && resolveAppHandle() ? managedPricingPlansUrl(session.shop) : null;
    const goToPlans = Boolean(plansUrl) && !onPlanPage && requiresPlanSelection({ billingEnabled, subscribed });
    if (goToPlans && isFullPageLoad(url)) throw redirect(plansUrl!, { target: "_top" });
    const support = resolveSupportConfig();
    // Markets whose server events are on hold, so every page can say so; the
    // Markets page shows its own copy from fresher data.
    const markets = await listMarkets(session.shop).then((r) => r.markets).catch(() => []);
    return {
      heldMarkets: markets.filter((m) => marketTileState(m) === "token_problem"),
      apiKey: process.env.SHOPIFY_API_KEY || "",
      plan: plan?.subscribed
        ? {
            name: plan.plan_name,
            pendingName: plan.pending_plan_name,
            changesOn: plan.pending_plan_handle ? plan.current_period_end : null,
          }
        : null,
      billingEnabled,
      subscribed,
      // An in-app navigation that must go to Shopify's plan page (see App).
      goToPlansUrl: goToPlans ? plansUrl : null,
      viber: support.viber, // { enabled, numberE164, label }
    };
  });
};

export default function App() {
  const { apiKey, viber, billingEnabled, heldMarkets, goToPlansUrl } = useLoaderData<typeof loader>();
  if (goToPlansUrl) {
    return (
      <AppProvider apiKey={apiKey}>
        <GoToShopifyPlans url={goToPlansUrl} />
      </AppProvider>
    );
  }
  const heldAlerts = heldEventAlerts(heldMarkets);
  // The overview and the Market pages show their own copy of the banner.
  const path = useLocation().pathname.replace(/\/$/, "");
  const onMarketsPage = path === "/app" || path.startsWith("/app/markets/");
  return (
    <AppProvider apiKey={apiKey}>
      <NavMenu>
        <Link to="/app" rel="home">Markets</Link>
        {billingEnabled ? <Link to="/app/billing">Plan</Link> : null}
        <Link to="/app/settings">Settings</Link>
        <Link to="/app/help">Help</Link>
      </NavMenu>
      {!onMarketsPage && heldAlerts.length ? (
        <div style={{ padding: "16px 16px 0" }}>
          <s-stack gap="small-200">
            {heldAlerts.map((alert) => (
              <s-banner key={alert.marketId} tone="critical" heading={alert.heading}>
                {alert.text} <Link to={`/app/markets/${alert.marketId}`}>View {alert.name}</Link>
              </s-banner>
            ))}
          </s-stack>
        </div>
      ) : null}
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
