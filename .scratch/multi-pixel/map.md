# Multi-Pixel: Meta pixel per Shopify Market

Label: wayfinder:map
Status: closed (destination reached, 2026-10-01)

## Destination

A **working POC app** installed on the dev store `gpay3y-2v.myshopify.com` (BG and GR Markets, one domain each). It sends the Standard Funnel browser events to the Market Pixel of whichever Market the shopper is in, **Purchase** included. Code: `shopify-app/` (run guide: `shopify-app/POC.md`).

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
- Stack: Shopify's React Router app template, Node/TypeScript, Prisma + **SQLite**, Docker.
- **Execution is carried in this map** (the user's call on 2026-09-30): build the POC now; tickets record decisions as they're made.
- Skills for grilling tickets: `grilling` + `domain-modeling`.
- Tracker: local markdown. Tickets are in `issues/`, research findings are in `research/` on `research/<name>` branches.

## Decisions so far

- **POC declared successful (2026-10-01, the user's call):** the destination is reached and this map is closed. Production design continues as a new effort; its brief is [../multi-pixel-app/brief.md](../multi-pixel-app/brief.md), which carries over this map's remaining Not yet specified items.
- **Content IDs and event shape (2026-10-01, grilled with the user):** match the Official Meta App exactly (observed live on colourpop.com): product IDs with `content_type: product_group` on every event, which matches AdFeed Market Catalogs' `item_group_id`. AddToCart `value` is the unit price, `content_category` is the product type, and ViewContent also fires on cart and collection pages. This closes [Which identifier goes into content_ids so events match the merchant's catalogs?](issues/05-content-ids-format.md).
- **Conversions API (2026-10-01, grilled with the user; research on branch `research/capi-and-content-ids`):** every Browser Event is relayed encrypted (RSA-OAEP + AES-GCM) to the backend and sent as a Server Event to the same Market Pixel with the same event ID. The token is pasted per Market Pixel, with an optional Test event code. Purchase joins the relayed browser Purchase (consent and Market) with the `orders/create` webhook (hashed customer data) on the order id, using event ID `purchase-<orderId>`. There's no server Purchase without a browser Purchase (cookie consent; `buyer_accepts_marketing` is email consent, not cookie consent). The backend rejects foreign Origins, unknown shops and unmapped market → pixel pairs. An Event log page shows what happened.

- **POC verified end to end (2026-09-30):** on `gpay3y-2v` the user confirmed the full Standard Funnel (PageView through Purchase) reaches the right Market Pixel for both the BG and GR Markets. The earlier missing checkout events were a Market configuration issue in the store, not the app.

<!-- one line per closed ticket: [title](issues/NN-slug.md): gist -->

- [Can a Web Pixel app extension detect the shopper's Market on every Standard Funnel event?](issues/01-market-detection-in-web-pixel.md): checkout events (including Purchase on the Thank you page) carry `checkout.localization.market.id`. Storefront events carry no Market, so they need another signal, such as a theme app embed.
- [What are the documented ways to fire a Purchase from the thank-you page?](issues/03-thank-you-page-fallback.md): script injection there is gone for every plan. The Web Pixel's `checkout_completed` is the Purchase route, and thank-you extensions could only reach Meta through our backend (the out-of-scope CAPI), so no fallback is needed.
- [Can Meta's pixel run inside the Web Pixel sandbox and address several pixels?](issues/02-meta-pixel-in-web-pixel-sandbox.md): `fbq` can't run in the strict sandbox. Send each event with `fetch` to Meta's `/tr` endpoint, which names one pixel per request, reusing or creating the shop's `_fbp` / `_fbc` cookies.
- [How does the pixel learn the shopper's Market on storefront events?](issues/07-storefront-market-signal.md): a theme app embed works out the Market in Liquid and sends PageView, ViewContent and Search itself (`fbq` `trackSingle`). It also leaves the market id in a cookie for the Web Pixel's AddToCart.
- [Where does the Pixel Mapping live, and how does the storefront pixel read it?](issues/04-where-pixel-mapping-lives.md): SQLite is the source of truth, mirrored on save to an app-owned metafield (theme embed) and to the Web Pixel's settings (checkout).

## Not yet specified

- **CAPI verification on `gpay3y-2v`**: deploy the Conversions API build and confirm in Events Manager that each Market Pixel shows browser and server events deduplicated (Purchase included), plus the match quality of server Purchases.


- **Admin UX for the Pixel Mapping**: how the merchant sees their Markets and assigns pixels, and what happens when Markets are added, renamed or deleted in Shopify after mapping.
- **Event shape per Standard Funnel event**: which parameters each event sends to Meta (value, currency, content_type, contents, event_id for future CAPI dedup) and how they're built from Shopify's event payloads.
- **App Store constraints**: review requirements that affect a pixel app (privacy declarations, GDPR webhooks, performance rules) and that the POC must not paint us out of. This includes whether to request protected customer data approval so advanced matching (hashed email and phone) can raise match quality.

## Out of scope

- [Set up a dev store with BG and RO Markets and capture real Web Pixel payloads](issues/06-dev-store-with-markets.md): superseded. The user chose to build the POC directly and verify against it instead of a throwaway probe.

- **Uninstall cleanup / pixel lifecycle**: the POC is temporary code (the user's call on 2026-09-30).
- **Pixel ID validation / Meta account connection**: manual entry only for the POC.
- **Creating or syncing per-market product catalogs**: the merchant's job (or another tool's). The app only has to send `content_ids` that match those catalogs.
- **Headless / Hydrogen storefronts**: Online Store only.
- **Monetization / billing**: to be discussed once the POC is confirmed working.
- **Guarding against merchant misconfiguration** (for example a clash with the Official Meta App's pixel): the merchant's responsibility.
