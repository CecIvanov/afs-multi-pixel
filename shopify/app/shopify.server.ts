import "@shopify/shopify-app-react-router/adapters/node";
import { ApiVersion, shopifyApp } from "@shopify/shopify-app-react-router/server";
import { LogSeverity } from "@shopify/shopify-api";
import { PrismaSessionStorage } from "@shopify/shopify-app-session-storage-prisma";

import prisma from "./db.server";
import { ensureBackendTenant } from "./tenant.server";
import { logError, logInfo } from "./logger.server";
import { resolveAppDistribution, resolveExpiringOfflineAccessTokens } from "./shopify-config.server";

const appDistribution = resolveAppDistribution();
const expiringOfflineAccessTokens = resolveExpiringOfflineAccessTokens(appDistribution);

const shopify = shopifyApp({
  apiKey: process.env.SHOPIFY_API_KEY,
  apiSecretKey: process.env.SHOPIFY_API_SECRET || "",
  apiVersion: ApiVersion.October25,
  scopes: process.env.SCOPES?.split(","),
  appUrl: process.env.SHOPIFY_APP_URL || "",
  authPathPrefix: "/auth",
  sessionStorage: new PrismaSessionStorage(prisma),
  distribution: appDistribution,
  logger: { level: LogSeverity.Error },
  future: { expiringOfflineAccessTokens },
  hooks: {
    afterAuth: async ({ session }) => {
      logInfo("after_auth", { shop: session.shop, is_online: session.isOnline });
      if (!session.accessToken) {
        logError("after_auth_tenant_skipped", new Error("missing access token"), { shop: session.shop });
        return;
      }
      try {
        // Upsert the canonical backend tenant with the fresh offline token so
        // background workers always read a current token from Postgres.
        const tenant = await ensureBackendTenant(session);
        logInfo("after_auth_tenant_synced", { shop: session.shop, tenant_id: tenant.id });
      } catch (error) {
        // Never block the merchant from loading the admin on a transient backend
        // hiccup — the next navigation heals the tenant.
        logError("after_auth_tenant_failed", error, { shop: session.shop });
      }
    },
  },
  ...(process.env.SHOP_CUSTOM_DOMAIN ? { customShopDomains: [process.env.SHOP_CUSTOM_DOMAIN] } : {}),
});

export default shopify;
export const apiVersion = ApiVersion.October25;
export const addDocumentResponseHeaders = shopify.addDocumentResponseHeaders;
export const authenticate = shopify.authenticate;
export const unauthenticated = shopify.unauthenticated;
export const login = shopify.login;
export const registerWebhooks = shopify.registerWebhooks;
export const sessionStorage = shopify.sessionStorage;
