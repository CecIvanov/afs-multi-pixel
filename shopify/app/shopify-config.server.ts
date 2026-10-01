import { AppDistribution } from "@shopify/shopify-app-react-router/server";

export function resolveAppDistribution(
  value: string | undefined = process.env.SHOPIFY_APP_DISTRIBUTION,
): AppDistribution {
  const normalized = String(value || "").trim().toLowerCase().replace(/-/g, "_");
  if (normalized === "single_merchant" || normalized === "singlemerchant") {
    return AppDistribution.SingleMerchant;
  }
  if (normalized === "shopify_admin" || normalized === "shopifyadmin") {
    return AppDistribution.ShopifyAdmin;
  }
  return AppDistribution.AppStore;
}

export function resolveExpiringOfflineAccessTokens(
  distribution: AppDistribution,
  value: string | undefined = process.env.SHOPIFY_EXPIRING_OFFLINE_TOKENS,
): boolean {
  const normalized = String(value || "").trim().toLowerCase();
  if (["0", "false", "no"].includes(normalized)) return false;
  if (["1", "true", "yes"].includes(normalized)) return true;
  // Public App Store apps use expiring offline tokens; custom Partner apps don't.
  return distribution === AppDistribution.AppStore;
}
