// Shopify App Pricing (managed pricing): the Partner API `activeSubscription` is
// the source of truth for a shop's plan (Shopify sends no subscription webhooks for
// managed pricing after 2026-04-28). Ported from the BG Delivery app.
// Needs SHOPIFY_APP_GID + SHOPIFY_PARTNER_ORG_ID (.env.<stack>) and
// SHOPIFY_PARTNER_ACCESS_TOKEN (.credentials.<stack>); Partner API 2026-07+.

export type PartnerSubscriptionSnapshot = {
  has_active_contract: boolean;
  effective_plan_handle: string | null;
  cancel_at_end_of_cycle: boolean;
};

type PartnerApiConfig = { appGid: string; partnerOrgId: string; accessToken: string };

function readPartnerApiConfig(): PartnerApiConfig {
  return {
    appGid: process.env.SHOPIFY_APP_GID?.trim() || "",
    partnerOrgId: process.env.SHOPIFY_PARTNER_ORG_ID?.trim() || "",
    accessToken: process.env.SHOPIFY_PARTNER_ACCESS_TOKEN?.trim() || "",
  };
}

export function isPartnerApiConfigured(config = readPartnerApiConfig()): boolean {
  return Boolean(config.appGid && config.partnerOrgId && config.accessToken);
}

const ACTIVE_SUBSCRIPTION = `#graphql
  query ActiveSubscription($appId: ID!, $shopId: ID!) {
    activeSubscription(appId: $appId, shopId: $shopId) {
      cancelAtEndOfCycle
      items { handle }
    }
  }
`;

export async function fetchPartnerSubscriptionSnapshot(shopGid: string): Promise<PartnerSubscriptionSnapshot> {
  const config = readPartnerApiConfig();
  if (!isPartnerApiConfigured(config)) throw new Error("The Partner API isn't configured");
  const version = process.env.SHOPIFY_PARTNER_API_VERSION?.trim() || "2026-07";
  const response = await fetch(`https://partners.shopify.com/${config.partnerOrgId}/api/${version}/graphql.json`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Shopify-Access-Token": config.accessToken },
    body: JSON.stringify({ query: ACTIVE_SUBSCRIPTION, variables: { appId: config.appGid, shopId: shopGid } }),
  });
  if (!response.ok) {
    throw new Error(`Partner API HTTP ${response.status}: ${(await response.text().catch(() => "")).slice(0, 300)}`);
  }
  const payload = (await response.json()) as {
    data?: { activeSubscription?: { cancelAtEndOfCycle?: boolean; items?: { handle?: string | null }[] } | null };
    errors?: { message: string }[];
  };
  if (payload.errors?.length) throw new Error(payload.errors.map((e) => e.message).join("; "));
  const subscription = payload.data?.activeSubscription;
  if (!subscription) return { has_active_contract: false, effective_plan_handle: null, cancel_at_end_of_cycle: false };
  const handle = (subscription.items ?? []).map((i) => i.handle?.trim().toLowerCase()).find(Boolean) ?? null;
  return {
    has_active_contract: true,
    effective_plan_handle: handle,
    cancel_at_end_of_cycle: subscription.cancelAtEndOfCycle === true,
  };
}

type AdminClient = { graphql: (query: string) => Promise<Response> };

/** The shop's GID (gid://shopify/Shop/<id>), which the Partner API query needs. */
export async function fetchShopGid(admin: AdminClient): Promise<string> {
  const response = await admin.graphql(`#graphql
    query MultiPixelShopId { shop { id } }`);
  const body = (await response.json()) as { data?: { shop?: { id?: string } } };
  const id = body.data?.shop?.id;
  if (!id) throw new Error("Shopify didn't return the shop's ID");
  return id;
}
