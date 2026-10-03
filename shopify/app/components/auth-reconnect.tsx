import { useEffect, useState } from "react";
import { recoverEmbeddedAdminAuth } from "../auth-recovery.client.mjs";

// Ported from BG Delivery. Shown when the app's frame inside the Shopify admin
// lands on "/" or "/auth/login" without Shopify's launch params: App Bridge
// re-embeds the app (/app) instead of the page getting stuck there.
// Render inside <AppProvider>, which loads App Bridge with the API key.
export function AuthReconnect({ appPath = "/app" }: { appPath?: string }) {
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    recoverEmbeddedAdminAuth(window, { appPath }).then((result) => {
      if (cancelled) return;
      if (result.outcome === "shopify_unavailable" || result.outcome === "missing_config") setFailed(true);
    });
    return () => {
      cancelled = true;
    };
  }, [appPath]);

  return (
    <s-page>
      <s-section>
        {failed ? (
          <s-stack gap="base">
            <s-text>AFS Multi Pixel couldn't reconnect to Shopify.</s-text>
            <s-button onClick={() => window.location.reload()}>Try again</s-button>
          </s-stack>
        ) : (
          <s-stack gap="base" direction="inline" alignItems="center">
            <s-spinner accessibilityLabel="Connecting to Shopify" />
            <s-text>Connecting to Shopify…</s-text>
          </s-stack>
        )}
      </s-section>
    </s-page>
  );
}
