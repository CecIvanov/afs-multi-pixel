// Managed-pricing helpers. Under managed pricing, plans live in the Partner
// Dashboard and merchants pick on Shopify's own page — the app just redirects
// there. Mode + app handle come from env (compose exports them from app.config.json).

export type BillingMode = "managed" | "api" | "disabled";

export function billingMode(): BillingMode {
  const raw = (process.env.SHOPIFY_BILLING_MODE || "managed").toLowerCase();
  return raw === "api" || raw === "disabled" ? (raw as BillingMode) : "managed";
}

export function usesManagedPricing(): boolean {
  return billingMode() === "managed";
}

export function resolveAppHandle(): string {
  return process.env.SHOPIFY_APP_HANDLE || process.env.APP_HANDLE || "";
}

/** The Shopify-hosted managed-pricing page for this app + store. */
export function managedPricingPlansUrl(shop: string): string {
  const store = shop.replace(/\.myshopify\.com$/i, "");
  return `https://admin.shopify.com/store/${store}/charges/${resolveAppHandle()}/pricing_plans`;
}
