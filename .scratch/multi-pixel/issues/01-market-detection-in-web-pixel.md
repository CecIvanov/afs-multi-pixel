# Can a Web Pixel app extension detect the shopper's Market on every Standard Funnel event?

Type: research
Label: wayfinder:research
Status: open
Map: [Multi-Pixel map](../map.md)

## Question

Inside a Shopify **Web Pixel app extension** (Online Store), what information identifies the shopper's current **Market** when each Standard Funnel customer event fires (`page_viewed`, `product_viewed`, `search_submitted`, `product_added_to_cart`, `checkout_started`, `payment_info_submitted`, `checkout_completed`)?

Specifically:
- Is a Market id or handle exposed directly (for example `checkout.localization.market`, `init.context`, or `document`/`navigator` data)? If not, what can we derive it from (country, language, currency, URL subfolder or domain, `localization` data), and how reliable is that mapping to a Shopify Market?
- Does `checkout_completed` fire for app pixels on the thank-you page in the native checkout (non-Plus stores too), and what localization or market data does its payload carry?
- Which product identifiers are in the event payloads (product id, variant id, SKU)? The `content_ids` ticket needs this.
- Anything about how the new Shopify Markets model (2025+) changes how Markets show up to pixels.

Answer with primary sources (shopify.dev Web Pixels API reference, customer events docs, changelog).
