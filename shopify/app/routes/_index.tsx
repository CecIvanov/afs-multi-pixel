import type { LoaderFunctionArgs } from "react-router";
import { redirect, useLoaderData } from "react-router";
import { AppProvider } from "@shopify/shopify-app-react-router/react";
import { AuthReconnect } from "../components/auth-reconnect";
import { resolveEmbeddedAuthRecovery } from "../auth-recovery.shared.mjs";
import { logInfo } from "../logger.server";

// "/" (as in BG Delivery): Shopify's launch params or a session token go on to
// /app; inside the admin frame without them, App Bridge re-embeds the app (never
// the landing page stuck in the admin); otherwise the public landing page.
export const loader = async ({ request }: LoaderFunctionArgs) => {
  const url = new URL(request.url);
  const recovery = resolveEmbeddedAuthRecovery({
    search: url.search,
    headers: request.headers,
    distribution: process.env.SHOPIFY_APP_DISTRIBUTION,
  });
  logInfo("index_route_recovery", { mode: recovery.kind, path: url.pathname, ...recovery.signals });
  if (recovery.kind === "redirect" && recovery.to) throw redirect(recovery.to);
  if (recovery.kind === "app-bridge") return { mode: "app-bridge" as const, apiKey: process.env.SHOPIFY_API_KEY || "" };
  return { mode: "landing" as const, apiKey: "" };
};

// The public landing page. Installation starts only from Shopify (App Store 2.3.1):
// no shop-domain form here.
export default function Index() {
  const data = useLoaderData<typeof loader>();
  if (data.mode === "app-bridge") {
    return (
      <AppProvider apiKey={data.apiKey}>
        <AuthReconnect />
      </AppProvider>
    );
  }
  return (
    <main style={{ fontFamily: "Inter, system-ui, sans-serif", maxWidth: 560, margin: "80px auto", padding: 24 }}>
      <h1>AFS Multi Pixel</h1>
      <p>A separate Meta pixel for every Shopify Market, with browser and server events.</p>
      <p>Install AFS Multi Pixel from the Shopify App Store, then open it from your Shopify admin.</p>
      <p>
        <a href="/privacy">Privacy policy</a> · <a href="/terms">Terms of service</a>
      </p>
    </main>
  );
}
