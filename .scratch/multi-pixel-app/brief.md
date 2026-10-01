# AFS Multi Pixel: from POC to production app (wayfinder brief)

Input for charting a new wayfinder map. The POC map ([../multi-pixel/map.md](../multi-pixel/map.md)) is closed as successful (2026-10-01). Everything below is either **settled** (proven or decided during the POC; don't re-open it without a reason) or **open** (candidates for the new map's frontier and fog). Vocabulary: `/CONTEXT.md` (Market, Market Pixel, Pixel Mapping, Standard Funnel, Official Meta App, Browser Event, Server Event, Relay, Market Catalog).

## Proposed destination (to confirm while charting)

A **build-ready spec** for the production version of AFS Multi Pixel, a public Shopify App Store app. It should be complete enough to slice into implementation issues: scope of v1, merchant UX, data model and hosting, Meta and Shopify integrations, compliance and App Store review, pricing and billing, and its relationship to AdFeed Studio.

## Business

### Problem
Merchants who sell in several Shopify Markets (for example BG, RO, GR) and run Meta ads per country use the **Official Meta App** (Facebook & Instagram channel). It sends every Market's events to **one pixel**, so Meta's optimisation mixes signals: a product that sells in BG gets promoted in RO, where other products sell. The fix is one Pixel ↔ Market Catalog ↔ Ads setup per Market. That needs events routed to a **separate pixel per Market**, which Shopify and Meta don't offer.

### What the app does
It detects the shopper's Market on every Standard Funnel event and sends the event to that Market's pixel, both from the browser and through the Conversions API (deduplicated). Event shape and `content_ids` match the Official Meta App, so existing catalogs and ad setups keep working.

### Relationship to AdFeed Studio (AFS)
- AFS builds per-market product feeds and catalogs. Its Market Catalogs use `id` = variant ID and `item_group_id` = product ID, which the app's `content_ids` (product IDs, `content_type: product_group`) match.
- The app is branded "AFS Multi Pixel" and hosted under `adfeedstudio.com`.
- **Open:** is it a standalone App Store product, an add-on bundled with AFS, or a funnel into AFS? This decides accounts, billing, onboarding and positioning.

### Open business questions
- Target merchants: multi-Market stores of any size, or a segment (for example CEE, Plus, agencies)? Which store languages and admin locales (EN/BG)?
- Pricing model: free, flat fee, per Market Pixel, per event volume, or tiers? Trial? Shopify Billing API (required for App Store apps that charge).
- Competition and positioning against the Official Meta App and multi-pixel apps already on the App Store. Why choose us (per-Market routing, CAPI included, AFS catalog fit)?
- Do merchants keep the Official Meta App installed alongside (for catalog sync or shops), and how do we stop double counting? The POC stance was "misconfiguration is the merchant's problem". Is that still acceptable for a paid public app?
- Support, onboarding and docs (help center, setup guide, verification checklist).
- Other ad platforms later (TikTok, Google)? It's probably out of scope for v1, but the decision affects naming and architecture.

## Technical: what the POC proved (settled)

Code: `shopify-app/` (about 1,600 lines; run guide `shopify-app/POC.md`). Verified end to end on the real store `gpay3y-2v.myshopify.com` (BG and GR Markets, one domain each): the full Standard Funnel, PageView through Purchase, reaches the right Market Pixel for each Market.

- **Stack:** Shopify React Router app template, Node/TypeScript, Prisma + SQLite, Docker, behind Caddy on a VPS. Admin API `2026-10`. Embedded admin app.
- **Market detection:**
  - Checkout events carry `checkout.localization.market.id`.
  - Storefront events carry no Market. A **theme app embed** reads `localization.market.id` in Liquid and writes it to the `_mpx_market` cookie.
  - Markets are keyed by numeric ID (Liquid gives a number, while the API and checkout give a `gid://`).
- **Who sends what:**
  - The theme embed sends PageView, ViewContent (product, cart, collection) and Search with `fbq('trackSingle')`.
  - The strict Web Pixel sends AddToCart (Market from the cookie), InitiateCheckout, AddPaymentInfo and Purchase (`checkout_completed`) with `fetch` to Meta's `/tr`.
  - It reuses or creates `_fbp` / `_fbc`, and sends facebook.com cookies along.
  - `fbq` can't run in the Web Pixel sandbox.
- **Pixel Mapping:**
  - SQLite (`MarketPixel`) is the source of truth.
  - On save it's mirrored to an app-owned metafield `multi_pixel.mapping` (read by the embed) and to the Web Pixel's `settings` (read by checkout).
  - Each Market has 0 or 1 pixel, and Markets may share a pixel. A Market without a pixel sends nothing (no fallback). Each event goes to the Market in effect when it fires.
- **Event shape:**
  - Identical to the Official Meta App: product IDs, `content_type: product_group` on every event, and `content_category` = product type.
  - AddToCart `value` is the unit price. `eid` is the Shopify event ID, and Purchase uses `purchase-<orderId>`.
- **Conversions API:**
  - Every Browser Event is relayed, encrypted (RSA-OAEP + AES-GCM, key pair in SQLite), to `/api/events`. The relay checks Origin against the shop's storefront hosts, checks that the shop is known, and checks that the market → pixel pair is in the mapping.
  - The relay sends the event to `graph.facebook.com/v26.0/<pixel>/events` with the same event ID, IP, UA and fbp/fbc, using the per-pixel CAPI token the merchant pasted. A Test event code is optional.
- **Purchase join:**
  - The relayed browser Purchase (Market + consent + cookies) is joined with the `orders/create` webhook (hashed email, phone, name and address) on the order ID (`PendingPurchase`).
  - There's no server Purchase without a browser Purchase, because the browser Purchase is the cookie-consent signal.
- **Consent:** Shopify Customer Privacy API plus the store's own banner. Events go out only with marketing consent. The app builds no banner.
- **Observability:** an Event log page (`EventLog`) shows each event as sent, skipped, waiting, rejected or error, with Meta's answer.
- **Distribution in the POC:** custom distribution. Protected customer data (name, email, phone, address) was self-serve there. It is **not** self-serve for a public app; it needs Shopify review.

## Technical: POC shortcuts that production must revisit (open)

- **Hosting and data:** SQLite on one VPS behind Caddy. Production database (Postgres?), multi-instance, backups, migrations, and where secrets and CAPI tokens live (encrypted at rest?). Key rotation for the relay key pair (today, "save again after deploy" is needed to republish the key and endpoint).
- **Scale and reliability of the relay plus CAPI:** synchronous send per event today. Do we need a queue or worker, retries, rate limits, batching, and dead-letter handling? `PendingPurchase` expiry (an order with no browser half)? `EventLog` retention and volume?
- **Meta connection:**
  - Pixel IDs and CAPI tokens are pasted by hand with no validation.
  - Production options: Meta Business Login / Facebook Login for Business to list pixels and generate tokens, or validated manual entry.
  - Meta app review, token expiry and error surfacing.
- **Admin UX:**
  - How the merchant sees Markets and assigns pixels.
  - What happens when Markets are added, renamed, deleted or merged after mapping (webhooks? `markets/*` topics?).
  - Onboarding checklist (embed switched on, consent banner present, Official Meta App conflict).
  - Health and verification view (beyond the raw Event log).
- **Theme embed dependency:** storefront events need the merchant to switch on the embed. Detecting it and guiding them, and what happens with themes that don't render it (headless stays out of scope?).
- **Market edge cases:** a shopper matching several Markets, B2B Markets, subfolder or domain shared by Markets, and storefront and checkout choosing different Markets.
- **Advanced matching in the browser:** hashed email or phone on `/tr` needs protected customer data. Do we want it for match quality?
- **App Store compliance:**
  - The mandatory GDPR webhooks (`customers/data_request`, `customers/redact`, `shop/redact`) are **not implemented yet**.
  - Uninstall cleanup is needed: metafield, web pixel, stored tokens and logs.
  - Protected customer data review for `orders/create` PII.
  - Privacy policy and data processing statement.
  - Built-for-Shopify performance rules for the theme embed.
  - Listing requirements.
- **Billing:** Shopify Billing API integration once pricing is decided.
- **Multi-tenant security:** relay abuse (rate limiting per shop and IP), Origin checks with custom domains added later, and token storage.
- **Testing:** there are no automated tests in the POC. What's the test strategy for the extensions (Liquid embed, strict Web Pixel), the relay and the CAPI join?
- **Code-level decisions kept from the POC vs rewrite:** is `shopify-app/` the base for production, or a reference?

## Out of scope (carried from the POC; reconfirm)

- Creating or syncing per-market catalogs (that's AFS's or the merchant's job).
- Headless / Hydrogen storefronts.
- Guarding against merchant misconfiguration (re-examine for a paid app; see the business questions above).

## Notes for the map

- Domain skills worth consulting in sessions: `grilling` + `domain-modeling` (default), `adfeedstudio:business-analyst` (requirements and personas), `adfeedstudio:sales` / `adfeedstudio:marketing` (pricing and positioning tickets), and `research` for Shopify App Store and Meta API facts.
- Tracker: local markdown, same convention as the POC (`.scratch/<effort>/map.md`, `issues/`, `research/<name>` branches).
- The POC's research branches (`research/market-detection-in-web-pixel`, `research/meta-pixel-in-web-pixel-sandbox`, `research/thank-you-page-fallback`, `research/capi-and-content-ids`) hold primary-source findings worth reusing.
