import prisma from "../db.server";
import {
  hashCustomer,
  sendToCapi,
  withoutEmpty,
  type CustomData,
  type ServerEvent,
} from "./capi.server";

// The storefront (theme embed + Web Pixel) relays every event it sends to Meta's browser pixel,
// encrypted, to /api/events. This module turns those into Conversions API events for the same
// Market Pixel with the same event ID, so Meta deduplicates the browser and server copies.
// Purchase is the exception: it waits for the orders/create webhook to add customer data.

export type StorefrontEvent = {
  shop: string;
  event: string; // Meta event name: PageView, ViewContent, Search, AddToCart, InitiateCheckout, AddPaymentInfo, Purchase
  eventId: string;
  eventTime?: number; // ms
  marketId: string;
  pixelId: string;
  url?: string;
  fbp?: string;
  fbc?: string;
  customData?: CustomData;
  orderId?: string; // Purchase only, numeric
};

export type RequestContext = { ip?: string; userAgent?: string; origin?: string | null };

const STOREFRONT_EVENTS = new Set([
  "PageView",
  "ViewContent",
  "Search",
  "AddToCart",
  "InitiateCheckout",
  "AddPaymentInfo",
  "Purchase",
]);

const log = (entry: {
  shop: string;
  source: "storefront" | "webhook";
  eventName: string;
  status: "sent" | "skipped" | "waiting" | "rejected" | "error";
  eventId?: string;
  marketId?: string;
  pixelId?: string;
  detail?: string;
  origin?: string | null;
}) => prisma.eventLog.create({ data: { ...entry, origin: entry.origin ?? undefined } });

export const numericId = (id: string | number | null | undefined) =>
  id === null || id === undefined ? "" : String(id).split("/").pop() ?? "";

export async function isAllowedOrigin(shop: string, origin: string | null) {
  // Web Pixels run in a sandboxed worker whose requests may carry `Origin: null`.
  if (!origin || origin === "null") return true;
  const config = await prisma.shopConfig.findUnique({ where: { shop } });
  if (!config) return false;
  const host = (() => {
    try {
      return new URL(origin).host;
    } catch {
      return "";
    }
  })();
  return (JSON.parse(config.allowedHosts) as string[]).includes(host);
}

export async function handleStorefrontEvent(raw: unknown, context: RequestContext) {
  const event = raw as StorefrontEvent;
  const shop = typeof event?.shop === "string" ? event.shop : "";
  const base = {
    shop: shop || "unknown",
    source: "storefront" as const,
    eventName: String(event?.event ?? "?"),
    eventId: event?.eventId,
    marketId: event?.marketId ? String(event.marketId) : undefined,
    pixelId: event?.pixelId ? String(event.pixelId) : undefined,
    origin: context.origin,
  };

  if (!shop || !STOREFRONT_EVENTS.has(event.event) || !event.eventId || !event.marketId) {
    await log({ ...base, status: "rejected", detail: "malformed event" });
    return;
  }
  if (!(await prisma.session.findFirst({ where: { shop } }))) {
    await log({ ...base, status: "rejected", detail: "shop has not installed the app" });
    return;
  }
  if (!(await isAllowedOrigin(shop, context.origin ?? null))) {
    await log({ ...base, status: "rejected", detail: `origin not allowed: ${context.origin}` });
    return;
  }

  const marketPixel = await prisma.marketPixel.findUnique({
    where: { shop_marketId: { shop, marketId: String(event.marketId) } },
  });
  if (!marketPixel || marketPixel.pixelId !== String(event.pixelId)) {
    await log({ ...base, status: "rejected", detail: "market/pixel not in this shop's Pixel Mapping" });
    return;
  }

  if (event.event === "Purchase") {
    await recordBrowserPurchase(event, context);
    return;
  }

  if (!marketPixel.capiToken) {
    await log({ ...base, status: "skipped", detail: "no CAPI token for this Market Pixel" });
    return;
  }

  const serverEvent: ServerEvent = {
    event_name: event.event,
    event_id: event.eventId,
    event_time: eventTimeSeconds(event.eventTime),
    event_source_url: event.url,
    action_source: "website",
    user_data: withoutEmpty({
      client_ip_address: context.ip,
      client_user_agent: context.userAgent,
      fbp: event.fbp,
      fbc: event.fbc,
    }),
    custom_data: event.customData ? withoutEmpty(event.customData) : undefined,
  };
  const result = await sendToCapi(
    marketPixel.pixelId,
    marketPixel.capiToken,
    serverEvent,
    marketPixel.testEventCode,
  );
  await log({ ...base, status: result.ok ? "sent" : "error", detail: result.detail });
}

const eventTimeSeconds = (ms?: number) => {
  const now = Math.floor(Date.now() / 1000);
  if (!ms) return now;
  const seconds = Math.floor(ms / 1000);
  // Meta rejects events older than 7 days or in the future.
  return seconds > now || now - seconds > 7 * 24 * 3600 ? now : seconds;
};

// --- Purchase: browser half + webhook half -------------------------------------------------------

type BrowserPurchase = StorefrontEvent & { ip?: string; userAgent?: string };

async function recordBrowserPurchase(event: StorefrontEvent, context: RequestContext) {
  const orderId = numericId(event.orderId);
  if (!orderId) {
    await log({
      shop: event.shop,
      source: "storefront",
      eventName: "Purchase",
      eventId: event.eventId,
      status: "rejected",
      detail: "Purchase without orderId",
      origin: context.origin,
    });
    return;
  }
  const browser: BrowserPurchase = { ...event, ip: context.ip, userAgent: context.userAgent };
  await prisma.pendingPurchase.upsert({
    where: { shop_orderId: { shop: event.shop, orderId } },
    create: { shop: event.shop, orderId, browser: JSON.stringify(browser) },
    update: { browser: JSON.stringify(browser) },
  });
  await completePurchase(event.shop, orderId, "storefront");
}

export async function handleOrderCreated(shop: string, order: Record<string, any>) {
  const orderId = numericId(order.id);
  await prisma.pendingPurchase.upsert({
    where: { shop_orderId: { shop, orderId } },
    create: { shop, orderId, order: JSON.stringify(order) },
    update: { order: JSON.stringify(order) },
  });
  await completePurchase(shop, orderId, "webhook");
}

async function completePurchase(shop: string, orderId: string, source: "storefront" | "webhook") {
  const pending = await prisma.pendingPurchase.findUnique({
    where: { shop_orderId: { shop, orderId } },
  });
  if (!pending || pending.sentAt) return;

  const eventId = `purchase-${orderId}`;
  if (!pending.browser || !pending.order) {
    await log({
      shop,
      source,
      eventName: "Purchase",
      eventId,
      status: "waiting",
      detail: pending.browser
        ? "browser Purchase received; waiting for orders/create"
        : "order received; waiting for the browser Purchase (none arrives without marketing consent)",
    });
    return;
  }

  const browser = JSON.parse(pending.browser) as BrowserPurchase;
  const order = JSON.parse(pending.order) as Record<string, any>;
  const marketPixel = await prisma.marketPixel.findUnique({
    where: { shop_marketId: { shop, marketId: String(browser.marketId) } },
  });
  const base = {
    shop,
    source,
    eventName: "Purchase",
    eventId,
    marketId: String(browser.marketId),
    pixelId: marketPixel?.pixelId,
  };
  if (!marketPixel?.capiToken) {
    await log({ ...base, status: "skipped", detail: "no CAPI token for this Market Pixel" });
    return;
  }

  // Claim the purchase before sending so a concurrent webhook/browser arrival doesn't send twice.
  const claimed = await prisma.pendingPurchase.updateMany({
    where: { id: pending.id, sentAt: null },
    data: { sentAt: new Date() },
  });
  if (claimed.count === 0) return;

  const result = await sendToCapi(
    marketPixel.pixelId,
    marketPixel.capiToken,
    purchaseEvent(eventId, browser, order),
    marketPixel.testEventCode,
  );
  if (!result.ok) {
    await prisma.pendingPurchase.update({ where: { id: pending.id }, data: { sentAt: null } });
  }
  await log({ ...base, status: result.ok ? "sent" : "error", detail: result.detail });
}

function purchaseEvent(
  eventId: string,
  browser: BrowserPurchase,
  order: Record<string, any>,
): ServerEvent {
  const address = order.billing_address ?? order.shipping_address ?? {};
  const lineItems: any[] = order.line_items ?? [];
  const presentment = order.total_price_set?.presentment_money;

  return {
    event_name: "Purchase",
    event_id: eventId,
    event_time: order.created_at
      ? Math.floor(new Date(order.created_at).getTime() / 1000)
      : Math.floor(Date.now() / 1000),
    event_source_url: browser.url,
    action_source: "website",
    user_data: withoutEmpty({
      ...hashCustomer({
        email: order.email ?? order.contact_email ?? order.customer?.email,
        phone: order.phone ?? address.phone ?? order.customer?.phone,
        firstName: address.first_name ?? order.customer?.first_name,
        lastName: address.last_name ?? order.customer?.last_name,
        city: address.city,
        provinceCode: address.province_code,
        zip: address.zip,
        countryCode: address.country_code,
        customerId: order.customer?.id ? String(order.customer.id) : undefined,
      }),
      client_ip_address: order.browser_ip ?? order.client_details?.browser_ip ?? browser.ip,
      client_user_agent: order.client_details?.user_agent ?? browser.userAgent,
      fbp: browser.fbp,
      fbc: browser.fbc,
    }),
    custom_data: withoutEmpty({
      content_ids: [...new Set(lineItems.map((item) => String(item.product_id)).filter(Boolean))],
      content_type: "product_group",
      value: Number(presentment?.amount ?? order.total_price),
      currency: presentment?.currency_code ?? order.presentment_currency ?? order.currency,
      num_items: lineItems.reduce((sum, item) => sum + Number(item.quantity ?? 0), 0),
      order_id: String(order.id),
    }),
  };
}
