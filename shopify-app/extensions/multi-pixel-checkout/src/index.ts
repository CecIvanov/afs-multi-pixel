import { register } from "@shopify/web-pixels-extension";
import type { Checkout, MoneyV2 } from "@shopify/web-pixels-extension";

// Sends AddToCart and the checkout events (InitiateCheckout, AddPaymentInfo, Purchase) to the
// Market Pixel. Theme code can't run in Shopify's checkout, so these come from this Web Pixel.
//
// Market:
//  - checkout events: the checkout's own localization.market;
//  - AddToCart: the `_mpx_market` cookie written by the theme app embed on the storefront.
//
// Meta's fbevents.js can't run in the strict sandbox (no DOM), so events go straight to Meta's
// /tr endpoint, one request per pixel.

const MARKET_COOKIE = "_mpx_market";

type PixelMapping = Record<string, string>;

const numericId = (id: string | null | undefined) =>
  id ? String(id).split("/").pop() ?? null : null;

const parseMapping = (raw: unknown): PixelMapping => {
  try {
    return typeof raw === "string" && raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
};

register(({ analytics, browser, settings }) => {
  const mapping = parseMapping(settings.mapping);

  const metaCookies = async () => {
    let fbp = await browser.cookie.get("_fbp");
    if (!fbp) {
      fbp = `fb.1.${Date.now()}.${Math.floor(Math.random() * 1e10)}`;
      await browser.cookie.set("_fbp", fbp);
    }
    const fbc = await browser.cookie.get("_fbc");
    return { fbp, fbc };
  };

  const send = async (
    event: { id: string; context: { document: { location: { href: string }; referrer: string } } },
    marketId: string | null,
    metaEvent: string,
    data: Record<string, string | number | undefined>,
  ) => {
    const pixelId = marketId ? mapping[marketId] : undefined;
    if (!pixelId) return;

    const { fbp, fbc } = await metaCookies();
    const params = new URLSearchParams({
      id: pixelId,
      ev: metaEvent,
      eid: event.id,
      dl: event.context.document.location.href,
      rl: event.context.document.referrer,
      ts: String(Date.now()),
      fbp,
    });
    if (fbc) params.set("fbc", fbc);
    for (const [key, value] of Object.entries(data)) {
      if (value !== undefined && value !== null && value !== "") {
        params.set(`cd[${key}]`, String(value));
      }
    }

    try {
      await fetch(`https://www.facebook.com/tr/?${params}`, {
        method: "GET",
        mode: "no-cors",
        keepalive: true,
      });
    } catch (error) {
      console.warn("[multi-pixel] send failed", metaEvent, error);
    }
  };

  const money = (value: MoneyV2 | null | undefined) => ({
    value: value?.amount,
    currency: value?.currencyCode,
  });

  analytics.subscribe("product_added_to_cart", async (event) => {
    const line = event.data.cartLine;
    if (!line) return;
    const marketId = numericId(await browser.cookie.get(MARKET_COOKIE));
    await send(event, marketId, "AddToCart", {
      content_ids: JSON.stringify([numericId(line.merchandise.product.id)]),
      content_type: "product_group",
      content_name: line.merchandise.product.title,
      num_items: line.quantity,
      ...money(line.cost.totalAmount),
    });
  });

  const checkoutData = (checkout: Checkout) => ({
    content_ids: JSON.stringify(
      (checkout.lineItems ?? [])
        .map((item) => numericId(item.variant?.product.id))
        .filter(Boolean),
    ),
    content_type: "product_group",
    num_items: (checkout.lineItems ?? []).reduce((sum, item) => sum + item.quantity, 0),
    ...money(checkout.totalPrice),
  });

  const checkoutMarket = (checkout: Checkout) => numericId(checkout.localization?.market?.id);

  analytics.subscribe("checkout_started", async (event) => {
    const { checkout } = event.data;
    await send(event, checkoutMarket(checkout), "InitiateCheckout", checkoutData(checkout));
  });

  analytics.subscribe("payment_info_submitted", async (event) => {
    const { checkout } = event.data;
    await send(event, checkoutMarket(checkout), "AddPaymentInfo", checkoutData(checkout));
  });

  analytics.subscribe("checkout_completed", async (event) => {
    const { checkout } = event.data;
    await send(event, checkoutMarket(checkout), "Purchase", {
      ...checkoutData(checkout),
      order_id: checkout.order?.id ?? undefined,
    });
  });
});
