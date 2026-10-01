import type { AdminApiContext } from "@shopify/shopify-app-react-router/server";
import prisma from "../db.server";
import { getPublicKey } from "./relay-crypto.server";

// The Pixel Mapping lives in SQLite (source of truth) and is mirrored to the two places the
// storefront reads it from, together with what the storefront needs for the encrypted relay
// (the app's public key and the /api/events endpoint):
//  - an app-owned metafield on the app installation, read by the theme app embed through Liquid
//    (`app.metafields.multi_pixel.config`): { pixels, publicKey, endpoint };
//  - the Web Pixel's settings: `mapping` (JSON of pixels), `publicKey`, `endpoint`.
// `pixels` is { "<numeric market id>": "<pixel id>" }. CAPI tokens never leave the server.

export const METAFIELD_NAMESPACE = "multi_pixel";
export const METAFIELD_KEY = "config";

export type Market = {
  id: string; // numeric market id
  name: string;
  handle: string;
  status: string;
  pixelId: string;
  capiToken: string;
  testEventCode: string;
};

export type MarketPixelInput = {
  id: string;
  name: string;
  pixelId: string;
  capiToken: string;
  testEventCode: string;
};

export type PixelMapping = Record<string, string>;

export const numericId = (gid: string) => gid.split("/").pop() ?? gid;

export async function listMarketsWithPixels(
  admin: AdminApiContext,
  shop: string,
): Promise<Market[]> {
  const response = await admin.graphql(
    `#graphql
      query multiPixelMarkets {
        markets(first: 100) {
          nodes {
            id
            name
            handle
            status
          }
        }
      }`,
  );
  const json = await response.json();
  const saved = await prisma.marketPixel.findMany({ where: { shop } });
  const rowByMarket = new Map(saved.map((row) => [row.marketId, row]));

  return (json.data?.markets.nodes ?? []).map((market) => {
    const id = numericId(market.id);
    return {
      id,
      name: market.name,
      handle: market.handle,
      status: market.status,
      pixelId: rowByMarket.get(id)?.pixelId ?? "",
      capiToken: rowByMarket.get(id)?.capiToken ?? "",
      testEventCode: rowByMarket.get(id)?.testEventCode ?? "",
    };
  });
}

export async function saveMarketPixels(
  admin: AdminApiContext,
  shop: string,
  markets: MarketPixelInput[],
): Promise<PixelMapping> {
  const mapping: PixelMapping = {};

  await prisma.$transaction(
    markets.map(({ id, name, pixelId, capiToken, testEventCode }) => {
      const trimmed = pixelId.trim();
      if (!trimmed) {
        return prisma.marketPixel.deleteMany({ where: { shop, marketId: id } });
      }
      mapping[id] = trimmed;
      const capi = {
        capiToken: capiToken.trim() || null,
        testEventCode: testEventCode.trim() || null,
      };
      return prisma.marketPixel.upsert({
        where: { shop_marketId: { shop, marketId: id } },
        create: { shop, marketId: id, marketName: name, pixelId: trimmed, ...capi },
        update: { marketName: name, pixelId: trimmed, ...capi },
      });
    }),
  );

  await saveAllowedHosts(admin, shop);
  await publishMapping(admin, mapping);
  return mapping;
}

// Storefront hosts the relay accepts as Origin: the myshopify domain, the primary domain and every
// Market's domains.
async function saveAllowedHosts(admin: AdminApiContext, shop: string) {
  const response = await admin.graphql(
    `#graphql
      query multiPixelHosts {
        shop {
          myshopifyDomain
          primaryDomain {
            host
          }
        }
        markets(first: 100) {
          nodes {
            webPresences(first: 20) {
              nodes {
                domain {
                  host
                }
              }
            }
          }
        }
      }`,
  );
  const json = await response.json();
  const hosts = new Set<string>([shop]);
  if (json.data?.shop.myshopifyDomain) hosts.add(json.data.shop.myshopifyDomain);
  if (json.data?.shop.primaryDomain?.host) hosts.add(json.data.shop.primaryDomain.host);
  for (const market of json.data?.markets.nodes ?? []) {
    for (const presence of market.webPresences.nodes) {
      if (presence.domain?.host) hosts.add(presence.domain.host);
    }
  }
  const allowedHosts = JSON.stringify([...hosts]);
  await prisma.shopConfig.upsert({
    where: { shop },
    create: { shop, allowedHosts },
    update: { allowedHosts },
  });
}

const relayEndpoint = () => `${process.env.SHOPIFY_APP_URL ?? ""}/api/events`;

async function publishMapping(admin: AdminApiContext, mapping: PixelMapping) {
  const publicKey = await getPublicKey();
  const endpoint = relayEndpoint();
  const value = JSON.stringify({ pixels: mapping, publicKey, endpoint });

  const installationResponse = await admin.graphql(
    `#graphql
      query multiPixelInstallation {
        currentAppInstallation {
          id
        }
      }`,
  );
  const installation = await installationResponse.json();
  const ownerId = installation.data!.currentAppInstallation.id;

  const metafieldResponse = await admin.graphql(
    `#graphql
      mutation multiPixelSetMapping($metafields: [MetafieldsSetInput!]!) {
        metafieldsSet(metafields: $metafields) {
          userErrors {
            field
            message
          }
        }
      }`,
    {
      variables: {
        metafields: [
          {
            ownerId,
            namespace: METAFIELD_NAMESPACE,
            key: METAFIELD_KEY,
            type: "json",
            value,
          },
        ],
      },
    },
  );
  const metafield = await metafieldResponse.json();
  throwOnUserErrors("metafieldsSet", metafield.data?.metafieldsSet?.userErrors);

  await upsertWebPixel(
    admin,
    JSON.stringify({ mapping: JSON.stringify(mapping), publicKey, endpoint }),
  );
}

async function upsertWebPixel(admin: AdminApiContext, settings: string) {
  const existingId = await findWebPixelId(admin);

  if (existingId) {
    const response = await admin.graphql(
      `#graphql
        mutation multiPixelUpdateWebPixel($id: ID!, $webPixel: WebPixelInput!) {
          webPixelUpdate(id: $id, webPixel: $webPixel) {
            userErrors {
              field
              message
            }
          }
        }`,
      { variables: { id: existingId, webPixel: { settings } } },
    );
    const json = await response.json();
    throwOnUserErrors("webPixelUpdate", json.data?.webPixelUpdate?.userErrors);
    return;
  }

  const response = await admin.graphql(
    `#graphql
      mutation multiPixelCreateWebPixel($webPixel: WebPixelInput!) {
        webPixelCreate(webPixel: $webPixel) {
          userErrors {
            field
            message
          }
        }
      }`,
    { variables: { webPixel: { settings } } },
  );
  const json = await response.json();
  throwOnUserErrors("webPixelCreate", json.data?.webPixelCreate?.userErrors);
}

// `webPixel` errors (rather than returning null) when the app has no pixel yet.
async function findWebPixelId(admin: AdminApiContext): Promise<string | null> {
  try {
    const response = await admin.graphql(
      `#graphql
        query multiPixelWebPixel {
          webPixel {
            id
          }
        }`,
    );
    const json = await response.json();
    return json.data?.webPixel?.id ?? null;
  } catch {
    return null;
  }
}

function throwOnUserErrors(
  operation: string,
  errors: { message: string }[] | undefined,
) {
  if (errors?.length) {
    throw new Error(`${operation}: ${errors.map((e) => e.message).join("; ")}`);
  }
}
