import { useEffect } from "react";
import type {
  ActionFunctionArgs,
  HeadersFunction,
  LoaderFunctionArgs,
} from "react-router";
import { Form, useActionData, useLoaderData, useNavigation } from "react-router";
import { useAppBridge } from "@shopify/app-bridge-react";
import { boundary } from "@shopify/shopify-app-react-router/server";
import { authenticate } from "../shopify.server";
import {
  listMarketsWithPixels,
  saveMarketPixels,
} from "../models/market-pixels.server";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { admin, session } = await authenticate.admin(request);
  const markets = await listMarketsWithPixels(admin, session.shop);
  return { markets };
};

export const action = async ({ request }: ActionFunctionArgs) => {
  const { admin, session } = await authenticate.admin(request);
  const form = await request.formData();

  const markets = form.getAll("marketId").map((id) => ({
    id: String(id),
    name: String(form.get(`marketName:${id}`) ?? ""),
    pixelId: String(form.get(`pixelId:${id}`) ?? ""),
  }));

  try {
    const mapping = await saveMarketPixels(admin, session.shop, markets);
    return { ok: true as const, mapping };
  } catch (error) {
    return { ok: false as const, error: String(error) };
  }
};

export default function Index() {
  const { markets } = useLoaderData<typeof loader>();
  const result = useActionData<typeof action>();
  const navigation = useNavigation();
  const shopify = useAppBridge();
  const saving = navigation.state === "submitting";

  useEffect(() => {
    if (result?.ok) shopify.toast.show("Pixel mapping saved");
    if (result && !result.ok) shopify.toast.show("Saving failed", { isError: true });
  }, [result, shopify]);

  return (
    <s-page heading="Market pixels">
      <Form method="post">
        <s-section heading="Meta pixel per Market">
          <s-paragraph>
            Shoppers in each Market send their events to that Market&apos;s
            Meta pixel. Leave a Market empty to send nothing for it.
          </s-paragraph>

          {markets.length === 0 ? (
            <s-paragraph>This store has no Markets yet.</s-paragraph>
          ) : (
            <s-stack direction="block" gap="base">
              {markets.map((market) => (
                <div key={market.id}>
                  <input type="hidden" name="marketId" value={market.id} />
                  <input
                    type="hidden"
                    name={`marketName:${market.id}`}
                    value={market.name}
                  />
                  <s-text-field
                    label={`${market.name} (${market.status.toLowerCase()})`}
                    name={`pixelId:${market.id}`}
                    defaultValue={market.pixelId}
                    placeholder="Meta pixel ID"
                    details={`Market ID ${market.id} · ${market.handle}`}
                  />
                </div>
              ))}
            </s-stack>
          )}

          {result && !result.ok && (
            <s-banner tone="critical" heading="Could not save">
              {result.error}
            </s-banner>
          )}
        </s-section>

        <s-section>
          <s-button type="submit" variant="primary" {...(saving ? { loading: true } : {})}>
            Save
          </s-button>
        </s-section>
      </Form>

      <s-section slot="aside" heading="Theme setup">
        <s-paragraph>
          Switch on the <s-text type="strong">Multi-Pixel</s-text> app embed in
          Online Store → Themes → Customize → App embeds. It sends PageView,
          ViewContent and Search. AddToCart and the checkout events (including
          Purchase) are sent by the app&apos;s pixel automatically.
        </s-paragraph>
      </s-section>
    </s-page>
  );
}

export const headers: HeadersFunction = (headersArgs) => {
  return boundary.headers(headersArgs);
};
