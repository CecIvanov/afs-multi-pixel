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
// /tr endpoint, one request per pixel. Each event is also relayed, encrypted, to the app's backend,
// which sends the same event (same event ID) to the Conversions API. Purchase uses the event ID
// `purchase-<order id>`, which the backend also derives from the orders/create webhook.
// Field shapes follow the Official Meta App.

const MARKET_COOKIE = "_mpx_market";

type PixelMapping = Record<string, string>;
type CustomData = {
  content_ids?: string[];
  content_type?: string;
  content_name?: string;
  content_category?: string;
  value?: number;
  currency?: string;
  num_items?: number;
  order_id?: string;
};
type PixelEvent = {
  id: string;
  context: { document: { location: { href: string }; referrer: string } };
};

const numericId = (id: string | null | undefined) =>
  id ? String(id).split("/").pop() ?? null : null;

const parseMapping = (raw: unknown): PixelMapping => {
  try {
    return typeof raw === "string" && raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
};

// --- encrypted relay (hybrid RSA-OAEP + AES-GCM), same envelope as the theme embed ---------------

const toB64 = (buffer: ArrayBuffer | Uint8Array) => {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
};

const fromB64 = (value: string) => {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
};

const encryptor = (publicKeyB64: string) => {
  let rsaKey: Promise<CryptoKey> | null = null;
  return async (payload: unknown) => {
    rsaKey ??= crypto.subtle.importKey(
      "spki",
      fromB64(publicKeyB64),
      { name: "RSA-OAEP", hash: "SHA-256" },
      false,
      ["encrypt"],
    );
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const aesKey = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, true, ["encrypt"]);
    const data = await crypto.subtle.encrypt(
      { name: "AES-GCM", iv },
      aesKey,
      new TextEncoder().encode(JSON.stringify(payload)),
    );
    const key = await crypto.subtle.encrypt(
      { name: "RSA-OAEP" },
      await rsaKey,
      await crypto.subtle.exportKey("raw", aesKey),
    );
    return JSON.stringify({ v: 1, k: toB64(key), iv: toB64(iv), d: toB64(data) });
  };
};

register(({ analytics, browser, settings, init }) => {
  const mapping = parseMapping(settings.mapping);
  const shop = init.data.shop.myshopifyDomain;
  const endpoint = typeof settings.endpoint === "string" ? settings.endpoint : "";
  const publicKey = typeof settings.publicKey === "string" ? settings.publicKey : "";
  const canRelay = Boolean(endpoint && publicKey && globalThis.crypto?.subtle);
  const encrypt = canRelay ? encryptor(publicKey) : null;
  if (!canRelay) console.warn("[multi-pixel] relay disabled (missing endpoint, key or WebCrypto)");

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
    event: PixelEvent,
    marketId: string | null,
    metaEvent: string,
    data: CustomData,
    options: { eventId?: string; orderId?: string } = {},
  ) => {
    const pixelId = marketId ? mapping[marketId] : undefined;
    console.info(`[multi-pixel] ${metaEvent} market ${marketId ?? "none"} -> pixel ${pixelId ?? "none (not sent)"}`);
    if (!pixelId || !marketId) return;

    const eventId = options.eventId ?? event.id;
    const { fbp, fbc } = await metaCookies();
    const params = new URLSearchParams({
      id: pixelId,
      ev: metaEvent,
      eid: eventId,
      dl: event.context.document.location.href,
      rl: event.context.document.referrer,
      ts: String(Date.now()),
      fbp,
    });
    if (fbc) params.set("fbc", fbc);
    for (const [key, value] of Object.entries(data)) {
      if (value === undefined || value === null || value === "") continue;
      params.set(`cd[${key}]`, Array.isArray(value) ? JSON.stringify(value) : String(value));
    }

    const toMeta = fetch(`https://www.facebook.com/tr/?${params}`, {
      method: "GET",
      mode: "no-cors",
      // Send the shopper's facebook.com cookies, like fbevents.js's image requests do: Meta uses
      // them to match the event to a person and to show it in Events Manager → Test Events.
      credentials: "include",
      keepalive: true,
    }).catch((error) => console.warn("[multi-pixel] send failed", metaEvent, error));

    const toBackend = encrypt
      ? encrypt({
          shop,
          event: metaEvent,
          eventId,
          eventTime: Date.now(),
          marketId,
          pixelId,
          url: event.context.document.location.href,
          fbp,
          fbc: fbc || undefined,
          customData: data,
          orderId: options.orderId,
        })
          .then((body) =>
            fetch(endpoint, {
              method: "POST",
              mode: "no-cors",
              keepalive: true,
              headers: { "Content-Type": "text/plain" },
              body,
            }),
          )
          .catch((error) => console.warn("[multi-pixel] relay failed", metaEvent, error))
      : Promise.resolve();

    await Promise.all([toMeta, toBackend]);
  };

  // Log instead of silently dropping the event when a handler throws.
  const safe =
    <E,>(name: string, handler: (event: E) => Promise<void>) =>
    async (event: E) => {
      try {
        await handler(event);
      } catch (error) {
        console.warn(`[multi-pixel] ${name} failed`, error);
      }
    };

  const money = (value: MoneyV2 | null | undefined) => ({
    value: value?.amount,
    currency: value?.currencyCode,
  });

  analytics.subscribe("product_added_to_cart", safe("product_added_to_cart", async (event) => {
    const line = event.data.cartLine;
    if (!line) return;
    const marketId = numericId(await browser.cookie.get(MARKET_COOKIE));
    const productId = numericId(line.merchandise.product.id);
    // Like the Official Meta App: value is the unit price, num_items the quantity added.
    await send(event, marketId, "AddToCart", {
      content_ids: productId ? [productId] : [],
      content_type: "product_group",
      content_name: line.merchandise.product.title ?? undefined,
      content_category: line.merchandise.product.type || undefined,
      num_items: line.quantity,
      ...money(line.merchandise.price),
    });
  }));

  const checkoutData = (checkout: Checkout): CustomData => ({
    content_ids: [
      ...new Set(
        (checkout.lineItems ?? [])
          .map((item) => numericId(item.variant?.product?.id))
          .filter((id): id is string => Boolean(id)),
      ),
    ],
    content_type: "product_group",
    num_items: (checkout.lineItems ?? []).reduce((sum, item) => sum + item.quantity, 0),
    ...money(checkout.totalPrice),
  });

  const checkoutMarket = (checkout: Checkout) => numericId(checkout.localization?.market?.id);

  analytics.subscribe("checkout_started", safe("checkout_started", async (event) => {
    const { checkout } = event.data;
    await send(event, checkoutMarket(checkout), "InitiateCheckout", checkoutData(checkout));
  }));

  analytics.subscribe("payment_info_submitted", safe("payment_info_submitted", async (event) => {
    const { checkout } = event.data;
    await send(event, checkoutMarket(checkout), "AddPaymentInfo", checkoutData(checkout));
  }));

  analytics.subscribe("checkout_completed", safe("checkout_completed", async (event) => {
    const { checkout } = event.data;
    const orderId = numericId(checkout.order?.id);
    await send(
      event,
      checkoutMarket(checkout),
      "Purchase",
      { ...checkoutData(checkout), order_id: orderId ?? undefined },
      orderId ? { eventId: `purchase-${orderId}`, orderId } : {},
    );
  }));
});
