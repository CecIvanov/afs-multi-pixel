import { type ActionFunctionArgs, type LoaderFunctionArgs, redirect, useLoaderData } from "react-router";
import { AppProvider } from "@shopify/shopify-app-react-router/react";
import { login } from "../shopify.server";
import { AuthReconnect } from "../components/auth-reconnect";
import { resolveEmbeddedAuthRecovery } from "../auth-recovery.shared.mjs";
import { logInfo } from "../logger.server";

// Where Shopify's library sends an /app request it can't authenticate (no session
// token, no launch params). As in BG Delivery: launch params or a token go back to
// /app; inside the admin frame App Bridge re-embeds the app; a plain browser visit
// gets Shopify's login handling (install starts from Shopify only).
export const loader = async ({ request }: LoaderFunctionArgs) => {
  const url = new URL(request.url);
  const recovery = resolveEmbeddedAuthRecovery({
    search: url.search,
    headers: request.headers,
    distribution: process.env.SHOPIFY_APP_DISTRIBUTION,
  });
  logInfo("auth_login_recovery", { mode: recovery.kind, path: url.pathname, ...recovery.signals });
  if (recovery.kind === "redirect" && recovery.to) throw redirect(recovery.to);
  if (recovery.kind === "app-bridge") return { apiKey: process.env.SHOPIFY_API_KEY || "" };
  await login(request);
  throw redirect("/");
};

export const action = async ({ request }: ActionFunctionArgs) => {
  return login(request);
};

export default function AuthLogin() {
  const { apiKey } = useLoaderData<typeof loader>();
  return (
    <AppProvider apiKey={apiKey}>
      <AuthReconnect />
    </AppProvider>
  );
}
