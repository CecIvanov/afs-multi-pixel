import { test } from "node:test";
import assert from "node:assert/strict";
import { addToCartData, checkoutData, numericId, purchaseData, purchaseEventId, trQuery } from "./meta-events.mjs";

const cartLine = {
  quantity: 3,
  cost: { totalAmount: { amount: 29.97, currencyCode: "EUR" } },
  merchandise: {
    price: { amount: 9.99, currencyCode: "EUR" },
    product: { id: "gid://shopify/Product/7", title: "Linen shirt", type: "Shirts" },
  },
};

const checkout = {
  order: { id: "gid://shopify/OrderIdentity/5551234" },
  totalPrice: { amount: 30, currencyCode: "EUR" },
  localization: { market: { id: "gid://shopify/Market/101" } },
  lineItems: [
    { quantity: 2, variant: { product: { id: "gid://shopify/Product/7" } } },
    { quantity: 1, variant: { product: { id: "gid://shopify/Product/8" } } },
    { quantity: 1, variant: { product: { id: "gid://shopify/Product/7" } } },
  ],
};

test("numericId keeps the numeric tail of a GID", () => {
  assert.equal(numericId("gid://shopify/Market/101"), "101");
  assert.equal(numericId("101"), "101");
  assert.equal(numericId(null), null);
});

test("AddToCart: the product ID, unit price as value, quantity as num_items", () => {
  assert.deepEqual(addToCartData(cartLine), {
    content_ids: ["7"],
    content_type: "product_group",
    content_name: "Linen shirt",
    content_category: "Shirts",
    num_items: 3,
    value: 9.99,
    currency: "EUR",
  });
});

test("checkout events: unique product IDs, item count and the checkout total", () => {
  assert.deepEqual(checkoutData(checkout), {
    content_ids: ["7", "8"],
    content_type: "product_group",
    num_items: 4,
    value: 30,
    currency: "EUR",
  });
});

test("Purchase adds the order ID and uses event ID purchase-<orderId>", () => {
  assert.equal(purchaseData(checkout).order_id, "5551234");
  assert.equal(purchaseEventId(checkout), "purchase-5551234");
  assert.equal(purchaseEventId({ order: null }), null);
});

test("trQuery builds Meta's /tr parameters with cd[] custom data", () => {
  const query = new URLSearchParams(
    trQuery({
      pixelId: "1290457710338842",
      event: "AddToCart",
      eventId: "e1",
      url: "https://dontmiss.bg/products/x",
      referrer: "",
      timestamp: 1000,
      fbp: "fb.1.1.2",
      fbc: undefined,
      data: addToCartData(cartLine),
    }),
  );
  assert.equal(query.get("id"), "1290457710338842");
  assert.equal(query.get("ev"), "AddToCart");
  assert.equal(query.get("eid"), "e1");
  assert.equal(query.get("cd[content_ids]"), '["7"]');
  assert.equal(query.get("cd[value]"), "9.99");
  assert.equal(query.get("cd[currency]"), "EUR");
  assert.equal(query.has("fbc"), false);
});
