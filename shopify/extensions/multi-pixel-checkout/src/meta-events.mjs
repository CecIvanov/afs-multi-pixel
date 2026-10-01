// Pure builders for the Web Pixel's Meta events, in the Official Meta App's shape
// (spec §3.1): content_ids are product IDs with content_type product_group,
// AddToCart's value is the unit price, Purchase's event ID is purchase-<orderId>.

/** @param {string | null | undefined} id */
export const numericId = (id) => (id ? String(id).split("/").pop() ?? null : null);

const withoutEmpty = (data) =>
  Object.fromEntries(Object.entries(data).filter(([, v]) => v !== undefined && v !== null && v !== ""));

export function addToCartData(line) {
  const product = line.merchandise?.product ?? {};
  const productId = numericId(product.id);
  return withoutEmpty({
    content_ids: productId ? [productId] : [],
    content_type: "product_group",
    content_name: product.title,
    content_category: product.type,
    num_items: line.quantity,
    value: line.merchandise?.price?.amount,
    currency: line.merchandise?.price?.currencyCode,
  });
}

export function checkoutData(checkout) {
  const items = checkout.lineItems ?? [];
  return withoutEmpty({
    content_ids: [...new Set(items.map((item) => numericId(item.variant?.product?.id)).filter(Boolean))],
    content_type: "product_group",
    num_items: items.reduce((sum, item) => sum + (item.quantity ?? 0), 0),
    value: checkout.totalPrice?.amount,
    currency: checkout.totalPrice?.currencyCode,
  });
}

export function purchaseData(checkout) {
  return withoutEmpty({ ...checkoutData(checkout), order_id: numericId(checkout.order?.id) });
}

/** The Purchase's event ID, shared with the Server Purchase so Meta keeps one. */
export function purchaseEventId(checkout) {
  const orderId = numericId(checkout.order?.id);
  return orderId ? `purchase-${orderId}` : null;
}

/** The query string for https://www.facebook.com/tr/ (what fbevents.js sends). */
export function trQuery({ pixelId, event, eventId, url, referrer, timestamp, fbp, fbc, data }) {
  const params = new URLSearchParams({
    id: pixelId,
    ev: event,
    eid: eventId,
    dl: url,
    rl: referrer ?? "",
    ts: String(timestamp),
  });
  if (fbp) params.set("fbp", fbp);
  if (fbc) params.set("fbc", fbc);
  for (const [key, value] of Object.entries(data)) {
    params.set(`cd[${key}]`, Array.isArray(value) ? JSON.stringify(value) : String(value));
  }
  return params.toString();
}
