# Set up a dev store with BG and RO Markets and capture real Web Pixel payloads

Type: task
Label: wayfinder:task
Status: claimed
Map: [Multi-Pixel map](../map.md)

## Question

Several decisions wait on real data rather than docs. Set up a Shopify dev store (Partner account) with at least two Markets (BG, RO), a few products with variants and SKUs, and a throwaway app with a Web Pixel extension that logs every Standard Funnel event payload plus `init`. Also add a theme app embed that logs `{{ localization.market.id }}`. Capture:

- the Market ID strings as seen by the pixel (`checkout.localization.market.id`), by Liquid, and by the Admin API `markets` query, and whether they match;
- the format of `variant.id`, `variant.product.id` and `variant.sku` in payloads (numeric or `gid://`);
- whether the storefront and checkout resolve the same Market for one shopper, including after switching country;
- whether a cookie or custom event from the embed is available to the pixel by the time it handles `page_viewed`.
- whether events sent from the sandbox with `fetch` to `https://www.facebook.com/tr` (with `eid`, `dl`, `ts`, `fbp`, `fbc` and `cd[content_ids]`) show up correctly in Meta Test Events for two different test pixels, and how Events Manager rates their match quality.

HITL: needs the human's Shopify Partner account. Record the store URL, where the payload logs are, and the facts above.

## Assets

- Probe app and checklist: [probe-app/README.md](../probe-app/README.md) (throwaway: a strict Web Pixel that logs payloads and sends to `/tr`, and a theme app embed that exposes `localization.market.id`).
- Captured logs go in `../probe-logs/`.
