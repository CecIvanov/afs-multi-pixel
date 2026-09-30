# What are the documented ways to fire a Purchase from the thank-you page?

Type: research
Label: wayfinder:research
Status: resolved
Map: [Multi-Pixel map](../map.md)

## Question

This is the backstop in case the Web Pixel route (ticket 01) can't deliver a Market-aware Purchase. What mechanisms does Shopify currently offer a **public app** to run code or send data on the **thank-you / order status page** after the native checkout?

- The status of "additional scripts" and `checkout.liquid` on the thank-you and order status pages (deprecation and sunset dates for Plus and non-Plus).
- Can Checkout UI extensions on the thank-you page (`purchase.thank-you.*` targets) make network calls to third parties or load scripts? What order and market or localization data can they read?
- Any other option available to a public app (app pixels via Customer Events, order status page extensions), and what each needs (Plus only? protected customer data approval?).

Answer with primary sources (shopify.dev, Shopify changelog, help center).

## Answer

Findings: branch `research/thank-you-page-fallback`, file `research/thank-you-page-fallback.md`.

- **No separate thank-you backdoor exists.** `checkout.liquid` and Additional scripts on the Thank you and Order status pages were sunset (2025-08-28 for Plus, 2026-08-26 for non-Plus, with the remaining stores upgraded automatically). Apps can't create order-status ScriptTags since 2025-02-01. An app can no longer inject `fbevents.js` there.
- **The Web Pixel is Shopify's documented replacement.** `checkout_completed` fires once per checkout on the Thank you page (or the first upsell page) and carries the Market id and handle, country, total, currency and order id. This is the Purchase route (see ticket 01).
- **Thank-you Checkout UI extensions** (`purchase.thank-you.*`) can make network calls (the `network_access` capability, approved automatically; the server needs CORS `*`), read the Market, lines, cost and order id, and `analytics.publish()` to Web Pixels. They can't load scripts or touch the page, and they render only if the merchant places them in the checkout editor. A Purchase from one can only go through our backend, which is effectively the out-of-scope CAPI work.
- **Order status page extensions** can make network calls too, but shoppers revisit that page, so they'd need de-duplication by order id. They're a weak fallback.
- **Plans and data approval:** no Plus requirement for the Thank you page is documented (inferred). Protected customer data approval is needed only for personal fields (since 2025-12-10 these are null without it), not for value, currency, products or Market.

Conclusion: the POC fires Purchase from the Web Pixel's `checkout_completed`. It doesn't need a thank-you-page fallback.
