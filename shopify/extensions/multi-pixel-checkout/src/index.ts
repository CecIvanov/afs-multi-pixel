import { register } from "@shopify/web-pixels-extension";
import {
  addToCartData,
  checkoutData,
  numericId,
  purchaseData,
  purchaseEventId,
  trQuery,
} from "./meta-events.mjs";

// The strict Web Pixel (spec §3.1): AddToCart and the checkout events
// (InitiateCheckout, AddPaymentInfo, Purchase) for the Market Pixel.
//
// Market:
//  - checkout events: the checkout's own localization.market;
//  - AddToCart: the `_mpx_market` cookie the theme app embed writes on the storefront.
//
// fbevents.js can't run in the strict sandbox (no DOM), so events go straight to
// Meta's /tr endpoint. Each one is also relayed, encrypted, to the app, which sends
// the same event (same event ID) to the Conversions API. Shopify runs this pixel
// only with marketing and sale-of-data consent (shopify.extension.toml).

const MARKET_COOKIE = "_mpx_market";

type PixelMapping = Record<string, string>;
type PixelEvent = {
  id: string;
  context: { document: { location: { href: string }; referrer: string } };
};

const parseMapping = (raw: unknown): PixelMapping => {
  try {
    return typeof raw === "string" && raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
};

// --- the encrypted Relay (RSA-OAEP + AES-GCM), same envelope as the theme embed ---
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
    rsaKey ??= crypto.subtle.importKey("spki", fromB64(publicKeyB64), { name: "RSA-OAEP", hash: "SHA-256" }, false, [
      "encrypt",
    ]);
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const aesKey = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, true, ["encrypt"]);
    const data = await crypto.subtle.encrypt(
      { name: "AES-GCM", iv },
      aesKey,
      new TextEncoder().encode(JSON.stringify(payload)),
    );
    const key = await crypto.subtle.encrypt({ name: "RSA-OAEP" }, await rsaKey, await crypto.subtle.exportKey("raw", aesKey));
    return JSON.stringify({ v: 1, k: toB64(key), iv: toB64(iv), d: toB64(data) });
  };
};

register(({ analytics, browser, settings, init }) => {
  const mapping = parseMapping(settings.mapping);
  const shop = init.data.shop.myshopifyDomain;
  const endpoint = typeof settings.endpoint === "string" ? settings.endpoint : "";
  const publicKey = typeof settings.publicKey === "string" ? settings.publicKey : "";
  const encrypt = endpoint && publicKey && globalThis.crypto?.subtle ? encryptor(publicKey) : null;

  // Reuse or create _fbp; reuse _fbc (spec §3.1).
  const metaCookies = async () => {
    let fbp = await browser.cookie.get("_fbp");
    if (!fbp) {
      fbp = `fb.1.${Date.now()}.${Math.floor(Math.random() * 1e10)}`;
      await browser.cookie.set("_fbp", fbp);
    }
    const fbc = (await browser.cookie.get("_fbc")) || undefined;
    return { fbp, fbc };
  };

  const send = async (
    event: PixelEvent,
    marketId: string | null,
    metaEvent: string,
    data: Record<string, unknown>,
    options: { eventId?: string | null; orderId?: string | null } = {},
  ) => {
    // A Market with no pixel sends nothing (spec §2).
    const pixelId = marketId ? mapping[marketId] : undefined;
    if (!pixelId || !marketId) return;

    const eventId = options.eventId ?? event.id;
    const { fbp, fbc } = await metaCookies();
    const url = event.context.document.location.href;
    const toMeta = fetch(
      `https://www.facebook.com/tr/?${trQuery({
        pixelId,
        event: metaEvent,
        eventId,
        url,
        referrer: event.context.document.referrer,
        timestamp: Date.now(),
        fbp,
        fbc,
        data,
      })}`,
      // Send the shopper's facebook.com cookies, like fbevents.js's requests do.
      { method: "GET", mode: "no-cors", credentials: "include", keepalive: true },
    ).catch(() => undefined);

    const toApp = encrypt
      ? encrypt({
          shop,
          event: metaEvent,
          eventId,
          eventTime: Date.now(),
          marketId,
          pixelId,
          url,
          fbp,
          fbc,
          customData: data,
          orderId: options.orderId ?? undefined,
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
          .catch(() => undefined)
      : Promise.resolve();

    await Promise.all([toMeta, toApp]);
  };

  const safe =
    <E,>(handler: (event: E) => Promise<void>) =>
    async (event: E) => {
      try {
        await handler(event);
      } catch (error) {
        console.warn("[afs-multi-pixel]", error);
      }
    };

  analytics.subscribe(
    "product_added_to_cart",
    safe(async (event) => {
      const line = event.data.cartLine;
      if (!line) return;
      const marketId = numericId(await browser.cookie.get(MARKET_COOKIE));
      await send(event, marketId, "AddToCart", addToCartData(line));
    }),
  );

  analytics.subscribe(
    "checkout_started",
    safe(async (event) => {
      const { checkout } = event.data;
      await send(event, numericId(checkout.localization?.market?.id), "InitiateCheckout", checkoutData(checkout));
    }),
  );

  analytics.subscribe(
    "payment_info_submitted",
    safe(async (event) => {
      const { checkout } = event.data;
      await send(event, numericId(checkout.localization?.market?.id), "AddPaymentInfo", checkoutData(checkout));
    }),
  );

  analytics.subscribe(
    "checkout_completed",
    safe(async (event) => {
      const { checkout } = event.data;
      await send(event, numericId(checkout.localization?.market?.id), "Purchase", purchaseData(checkout), {
        eventId: purchaseEventId(checkout),
        orderId: numericId(checkout.order?.id),
      });
    }),
  );
});
