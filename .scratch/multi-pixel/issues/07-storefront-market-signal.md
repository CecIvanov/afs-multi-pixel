# How does the pixel learn the shopper's Market on storefront events?

Type: grilling
Label: wayfinder:grilling
Status: resolved
Blocked by: 02
Map: [Multi-Pixel map](../map.md)

## Question

Storefront events (`page_viewed`, `product_viewed`, `search_submitted`, `product_added_to_cart`) don't carry the Market, while checkout events do (see ticket 01). How does the app give the pixel the Market ID for storefront events?

Candidates:
- a **theme app embed** that renders `{{ localization.market.id }}` and hands it to the pixel, either through a first-party cookie read with `browser.cookie.get` or through `Shopify.analytics.publish` custom events;
- the embed sending events to Meta itself, with no Web Pixel for storefront events;
- deriving the Market from the `localization` cookie or country through a mapping table (fallback only).

Also decide what happens when the embed is switched off (drop storefront events, or fall back), and how the merchant is guided to switch it on. This hangs on what the sandbox can do with cookies and network calls (ticket 02).

## Answer

Decided by the user on 2026-09-30, while directing the POC build: the **theme app embed** owns the storefront.
- It works out the Market in Liquid (`localization.market.id`), looks up the Market Pixel in the app-owned metafield, and sends PageView, ViewContent and Search itself with `fbq('trackSingle', pixelId, ...)`. `trackSingle` avoids leaking events into any other pixel on the page.
- It writes the market id to the `_mpx_market` cookie. The Web Pixel reads that cookie for AddToCart, which it handles because add-to-cart is theme-specific on the page.
- Embed switched off: no storefront events, and AddToCart has no market, so nothing is sent. The admin page's aside tells the merchant to switch the embed on.

Built in `shopify-app/extensions/multi-pixel-embed` and `shopify-app/extensions/multi-pixel-checkout`.
