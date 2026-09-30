# Multi-Pixel: Meta pixel per Shopify Market

Label: wayfinder:map

## Destination

An implementation-ready **POC spec** for a public Shopify app that sends the Standard Funnel browser pixel events to the Market Pixel of whichever Market the shopper is in. Along the way it proves that this is feasible, above all for **Purchase**, without controlling Shopify's native checkout.

## Notes

- Why the app exists: the Official Meta App sends every Market's events to one pixel, so Meta promotes products that are popular in one Market (a t-shirt in BG) inside another (RO, where pants sell). The fix is one Pixel ↔ Catalog ↔ Ads setup per Market.
- The vocabulary lives in `/CONTEXT.md` (Market, Market Pixel, Pixel Mapping, Standard Funnel, Official Meta App). Use those terms.
- The app's only job: **detect the shopper's Market and send the event to that Market's pixel.** Misconfiguration is the merchant's problem. For example, if a Market Pixel is also the Official Meta App's pixel, the app does not guard against it.
- Pixel Mapping: each Market has 0 or 1 Market Pixel, and several Markets may share one pixel. A Market with no pixel sends nothing (no fallback pixel).
- Each event goes to the Market in effect **when it fires**, so a journey that spans Markets splits across pixels.
- Browser pixel only, covering the full Standard Funnel (PageView, ViewContent, Search, AddToCart, InitiateCheckout, AddPaymentInfo, Purchase).
- Pixel IDs are entered by hand with no validation (POC).
- Consent comes from Shopify's Customer Privacy API and the store's own banner. The app builds no banner.
- Public Shopify App Store app, Online Store themes only.
- Stack: Shopify's React Router app template, Node/TypeScript, Prisma + Postgres.
- Skills for grilling tickets: `grilling` + `domain-modeling`.
- Tracker: local markdown. Tickets are in `issues/`, research findings are in `research/` on `research/<name>` branches.

## Decisions so far

<!-- one line per closed ticket: [title](issues/NN-slug.md): gist -->

- [Can a Web Pixel app extension detect the shopper's Market on every Standard Funnel event?](issues/01-market-detection-in-web-pixel.md): checkout events (including Purchase on the Thank you page) carry `checkout.localization.market.id`. Storefront events carry no Market, so they need another signal, such as a theme app embed.
- [What are the documented ways to fire a Purchase from the thank-you page?](issues/03-thank-you-page-fallback.md): script injection there is gone for every plan. The Web Pixel's `checkout_completed` is the Purchase route, and thank-you extensions could only reach Meta through our backend (the out-of-scope CAPI), so no fallback is needed.
- [Can Meta's pixel run inside the Web Pixel sandbox and address several pixels?](issues/02-meta-pixel-in-web-pixel-sandbox.md): `fbq` can't run in the strict sandbox. Send each event with `fetch` to Meta's `/tr` endpoint, which names one pixel per request, reusing or creating the shop's `_fbp` / `_fbc` cookies.

## Not yet specified

- **Admin UX for the Pixel Mapping**: how the merchant sees their Markets and assigns pixels, and what happens when Markets are added, renamed or deleted in Shopify after mapping.
- **Pixel lifecycle**: how the app's pixel is activated on install, kept in sync when the mapping changes, and removed on uninstall. The shape depends on where the mapping lives.
- **Event shape per Standard Funnel event**: which parameters each event sends to Meta (value, currency, content_type, contents, event_id for future CAPI dedup) and how they're built from Shopify's event payloads.
- **POC verification**: how we prove end-to-end that a shopper in RO lands in the RO pixel and one in BG in the BG pixel, including Purchase (test store, Markets setup, Meta Test Events).
- **App Store constraints**: review requirements that affect a pixel app (privacy declarations, GDPR webhooks, performance rules) and that the POC must not paint us out of. This includes whether to request protected customer data approval so advanced matching (hashed email and phone) can raise match quality.

## Out of scope

- **Conversions API (CAPI) and Meta OAuth**: browser pixel only for the POC. The spec should still leave room for an `event_id` so CAPI dedup can be added later.
- **Pixel ID validation / Meta account connection**: manual entry only for the POC.
- **Creating or syncing per-market product catalogs**: the merchant's job (or another tool's). The app only has to send `content_ids` that match those catalogs.
- **Headless / Hydrogen storefronts**: Online Store only.
- **Monetization / billing**: to be discussed once the POC is confirmed working.
- **Guarding against merchant misconfiguration** (for example a clash with the Official Meta App's pixel): the merchant's responsibility.
