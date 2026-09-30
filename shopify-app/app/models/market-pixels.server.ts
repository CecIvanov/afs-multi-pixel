import type { AdminApiContext } from "@shopify/shopify-app-react-router/server";
import prisma from "../db.server";

// The Pixel Mapping lives in SQLite (source of truth) and is mirrored to the two places the
// storefront reads it from:
//  - an app-owned metafield on the app installation, read by the theme app embed through Liquid
//    (`app.metafields.multi_pixel.mapping`);
//  - the Web Pixel's settings, read by the checkout-side pixel as `settings.mapping`.
// Both mirrors hold the same JSON: { "<numeric market id>": "<pixel id>" }.

export const METAFIELD_NAMESPACE = "multi_pixel";
export const METAFIELD_KEY = "mapping";

export type Market = {
  id: string; // numeric market id
  name: string;
  handle: string;
  status: string;
  pixelId: string;
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
  const pixelByMarket = new Map(saved.map((row) => [row.marketId, row.pixelId]));

  return (json.data?.markets.nodes ?? []).map((market) => {
    const id = numericId(market.id);
    return {
      id,
      name: market.name,
      handle: market.handle,
      status: market.status,
      pixelId: pixelByMarket.get(id) ?? "",
    };
  });
}

export async function saveMarketPixels(
  admin: AdminApiContext,
  shop: string,
  markets: { id: string; name: string; pixelId: string }[],
): Promise<PixelMapping> {
  const mapping: PixelMapping = {};

  await prisma.$transaction(
    markets.map(({ id, name, pixelId }) => {
      const trimmed = pixelId.trim();
      if (!trimmed) {
        return prisma.marketPixel.deleteMany({ where: { shop, marketId: id } });
      }
      mapping[id] = trimmed;
      return prisma.marketPixel.upsert({
        where: { shop_marketId: { shop, marketId: id } },
        create: { shop, marketId: id, marketName: name, pixelId: trimmed },
        update: { marketName: name, pixelId: trimmed },
      });
    }),
  );

  await publishMapping(admin, mapping);
  return mapping;
}

async function publishMapping(admin: AdminApiContext, mapping: PixelMapping) {
  const value = JSON.stringify(mapping);

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

  await upsertWebPixel(admin, JSON.stringify({ mapping: value }));
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
