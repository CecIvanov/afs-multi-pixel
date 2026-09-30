# Can a Web Pixel app extension detect the shopper's Market on every Standard Funnel event?

Type: research
Label: wayfinder:research
Status: resolved
Map: [Multi-Pixel map](../map.md)

## Question

Inside a Shopify **Web Pixel app extension** (Online Store), what information identifies the shopper's current **Market** when each Standard Funnel customer event fires (`page_viewed`, `product_viewed`, `search_submitted`, `product_added_to_cart`, `checkout_started`, `payment_info_submitted`, `checkout_completed`)?

Specifically:
- Is a Market id or handle exposed directly (for example `checkout.localization.market`, `init.context`, or `document`/`navigator` data)? If not, what can we derive it from (country, language, currency, URL subfolder or domain, `localization` data), and how reliable is that mapping to a Shopify Market?
- Does `checkout_completed` fire for app pixels on the thank-you page in the native checkout (non-Plus stores too), and what localization or market data does its payload carry?
- Which product identifiers are in the event payloads (product id, variant id, SKU)? The `content_ids` ticket needs this.
- Anything about how the new Shopify Markets model (2025+) changes how Markets show up to pixels.

Answer with primary sources (shopify.dev Web Pixels API reference, customer events docs, changelog).

## Answer

Findings: branch `research/market-detection-in-web-pixel`, file `research/market-detection-in-web-pixel.md`.

- **Checkout events carry the Market.** `checkout_started`, `payment_info_submitted` and `checkout_completed` include `event.data.checkout.localization.market.{id,handle}`, plus country and language. They need Checkout Extensibility, which every store has now that the non-Plus deadline (2026-08-26) has passed. That last point is inferred.
- **Storefront events don't carry the Market.** `page_viewed`, `product_viewed`, `search_submitted`, `product_added_to_cart` and `init` have no market, country or localization field.
- **Purchase:** `checkout_completed` fires for app pixels on the Thank you page (or the first upsell page) on every plan, so the thank-you-page idea is covered by the Web Pixel itself.
- **Product IDs:** events carry `variant.id`, `variant.sku` and `variant.product.id`. Whether these are numeric or `gid://` must be checked in real payloads.
- **New Markets model:** a shopper can match several Markets. Shopify picks the most specific (B2B, then retail, then region, then default), and a domain or subfolder can belong to several Markets. Guessing the Market from URL, country or currency is unreliable.
- **Recommended:** checkout events use `checkout.localization.market.id` (not the handle). Storefront events get the Market from a theme app embed that renders `{{ localization.market.id }}` from Liquid and passes it to the pixel (through a cookie or `Shopify.analytics.publish`). The catch is that the merchant must switch the embed on.
- **Needs verifying on a test store:**
  - Whether the pixel, Liquid and Admin API market IDs match.
  - Whether the storefront and checkout pick the same Market.
  - Whether the embed's signal arrives before `page_viewed` is handled.
  - Whether setting a cookie needs consent.
