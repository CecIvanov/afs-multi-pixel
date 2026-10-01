# AFS Multi Pixel v1: build spec

Status: signed off by the user (2026-10-01). Map: [map.md](map.md). Vocabulary: [/CONTEXT.md](../../CONTEXT.md). Decisions that are hard to reverse: [/docs/adr](../../docs/adr).

Every section points to the ticket that holds the decision and its reasoning. This spec restates the outcome only.

## 1. Product

AFS Multi Pixel is a **standalone, paid, public Shopify App Store app** ([01](issues/01-afs-relationship.md)). It sends each Standard Funnel event to the **Market Pixel** of the Market the shopper is in, from the browser and through the Conversions API, deduplicated. That gives each Market its own Pixel ↔ Market Catalog ↔ Ads setup, which the Official Meta App can't do.

- **Who it's for:** any Online Store merchant with two or more Markets. No segment-specific features ([02](issues/02-target-merchants.md)).
- **Language:** English only (admin UI, listing, help pages).
- **Brand and hosting:** "AFS Multi Pixel", hosted under `adfeedstudio.com`. No AdFeed Studio account and no link to one.
- **Pricing:** one paid plan, no trial, billed by Shopify ([09](issues/09-pricing-and-billing.md)).
- **Positioning** ([05](issues/05-competitors.md)): per-Market routing is the core product, not a top tier. It includes server events, an event shape identical to the Official Meta App so Market Catalogs keep matching, and a natural fit with AFS Market Catalogs.

### Out of scope for v1

- Creating or syncing catalogs.
- Headless / Hydrogen storefronts.
- Other ad platforms (keep names and architecture platform-neutral where it's free).
- Meta login.
- Browser-side advanced matching.
- The Built for Shopify badge.
- Detecting or warning about the Official Meta App ([11](issues/11-official-meta-app-conflict-policy.md)).
- Parent → child pixel inheritance.
- Writing help-center content (this spec only fixes what it must cover).

## 2. Routing rules

Inherited from the POC and unchanged ([POC map](../multi-pixel/map.md)):

- The **Pixel Mapping** gives each Market 0 or 1 Market Pixel. Markets may share a pixel.
- A mapped Market always has a **pixel ID + Conversions API token pair**. One without the other can't be saved ([10](issues/10-meta-connection-method.md), [ADR 0002](../../docs/adr/0002-manual-pixel-and-capi-token-per-market.md)).
- A Market with no pixel sends **nothing**. There's no fallback pixel and no inheritance from a parent Market.
- Each event goes to the Market in effect **when it fires**, so a journey that changes Market splits across pixels.
- Markets are keyed by the **numeric** Market ID. GIDs (Admin API, checkout) are normalised to the numeric tail.
- No special logic for B2B Markets, Draft Markets, shared domains, or the storefront and checkout reporting different Markets. The event follows the Market Shopify reports ([20](issues/20-market-edge-cases.md)).
- Market detection on the storefront uses Liquid `localization.market`, a known deprecated dependency ([15](issues/15-market-id-stability.md), [ADR 0001](../../docs/adr/0001-storefront-market-from-deprecated-liquid-localization-market.md)).

## 3. Event pipeline

### 3.1 Browser Events (from the POC)

| Event | Sent by | Market from | How |
|---|---|---|---|
| PageView, ViewContent (product, cart, collection), Search | Theme app embed | Liquid `localization.market.id` | `fbq('trackSingle', <pixel>, …)` |
| AddToCart | Strict Web Pixel | `_mpx_market` cookie written by the embed | `fetch` to Meta `/tr` |
| InitiateCheckout, AddPaymentInfo, Purchase (`checkout_completed`) | Strict Web Pixel | `checkout.localization.market.id` | `fetch` to Meta `/tr` |

- **Event shape:** identical to the Official Meta App.
  - `content_ids` = product IDs and `content_type: product_group` on every event.
  - `content_category` = product type.
  - AddToCart `value` = unit price.
  - `eid` = the Shopify event ID; Purchase uses `purchase-<orderId>`.
- **Cookies:** reuse or create `_fbp` / `_fbc`, and send facebook.com cookies along with `/tr` requests.
- **Consent:** no event without marketing consent.
  - The embed loads `fbevents.js` only when `customerPrivacy.marketingAllowed()` **and** `saleOfDataAllowed()` are true ([13](issues/13-compliance-plan.md)).
  - The app builds no cookie banner; the store's own banner is used.
- **No customer data** in Browser Events.

### 3.2 Relay and Server Events ([17](issues/17-relay-reliability.md))

1. Every Browser Event also goes to the backend as a **Relay** (`POST /api/events`), encrypted with RSA-OAEP + AES-GCM using the app's public key.
2. The endpoint decrypts and validates it, **stores** it in Postgres and answers. It sends nothing itself.
   - It rejects requests whose Origin isn't one of the shop's storefront domains, unknown shops, and market → pixel pairs that aren't in the mapping.
   - It's rate-limited per shop and per IP; the numbers are set during the build.
3. A **worker** sends stored events to `graph.facebook.com/v26.0/<pixel>/events` with the same event ID, IP, user agent and `fbp`/`fbc`, the Market's token, and the optional test event code.
   - **Retries** back off at 1 min, 5 min, 30 min, 2 h and 6 h. After that the event is **failed** and shows in the event log.
   - **Rejected token** (for example OAuthException 190): the Market's Server Events are **paused**. They stay stored and are sent once the token is replaced, if they're under 7 days old (Meta's limit). Browser Events continue. The Market's tile shows "Token problem".
4. **Purchase join:** the relayed browser Purchase (Market, consent, cookies) is joined with the `orders/create` webhook on the order ID. Like every webhook, it's stored first and processed by the worker (§5).
   - The Server Purchase uses event ID `purchase-<orderId>` and **hashed** email, phone, name and address from the order.
   - **No browser Purchase, no Server Purchase**: the browser Purchase is the consent signal.
   - An unmatched pending Purchase expires after **7 days**.

## 4. Merchant admin UX ([14](issues/14-onboarding-and-mapping-ux.md))

Variant C, "Market health", is the chosen design. Prototype: branch `prototype/admin-ux`, `.scratch/multi-pixel-app/prototype/admin-ux-prototype.html` (open `#C`).

- **Home is the Markets page.** The page header has the plan badge and an "Event log" button.
- **Setup strip**, shown until every step is done, with links to help and support ([22](issues/22-support-and-docs.md)):
  - App embed: read with `app.extensions()` on the published theme, with the activation deep link `/admin/themes/current/editor?context=apps&activateAppId={api_key}/{handle}`.
  - Pixels: at least one Market mapped.
  - Consent: the store's banner, with guidance.
  - Verified in Meta: the merchant confirms in Events Manager.
- **Summary row:** Markets sending (n of total), Markets needing attention, Browser Events in the last 24 h, and the share of them that reached Meta by server.
- **One tile per Market:**
  - **Mapped:** name and regions, status badge (Sending / Token problem), pixel name and ID, the error text if any, a 24-hour events-per-hour chart, Browser / Server / Purchase counts, last event, "Edit pixel" (or "Update token"), and "View events".
  - **Unmapped:** a dashed tile saying "No events are sent for shoppers in this Market", with "Add pixel". A **new** Market (from `markets/create` or a re-fetch) says when it was added and gets the primary button. B2B and Draft Markets are labelled and otherwise ordinary.
- **Pixel editor (modal):**
  - Pixel ID (15–16 digits) and Conversions API token, **both required**, plus an optional test event code.
  - **"Check with Meta"** must pass before Save: `GET /<pixel>?fields=id,name,owner_business,is_unavailable` with the token. It shows the pixel name and owner.
  - "Remove pixel" unmaps the Market.
- **Event log (side drawer):** all events, or one Market's from its tile. Columns: time, event, Market, sent as (Browser / Server / Relay), status (sent, skipped, waiting, rejected, failed or error), Meta's answer. Kept for 30 days.

## 5. Shopify integration

- **Two apps from one codebase** ([18](issues/18-poc-code-reuse.md)):
  - The **UAT App** (custom distribution, test stores only).
  - The **Production App** (public listing).
  - Each has its own app config, client ID and deployment.
- **Admin API** `2026-10`, embedded app, Shopify React Router app template, Node/TypeScript, Prisma.
- **Scopes:** `read_markets`, `write_pixels`, `read_customer_events`, `read_orders`. Confirm during the build whether reading the shop's domains needs more.
- **Extensions:**
  - A theme app embed (Liquid + `fbevents.js`).
  - A strict Web Pixel. Its settings carry the mapping and the Relay endpoint and public key.
- **App-owned metafield** `multi_pixel.mapping`: the mapping, the Relay endpoint and the public key, mirrored from Postgres on every save and on app start.
- **Webhooks: store, answer 200, process later** ([17](issues/17-relay-reliability.md)). Every webhook is HMAC-verified (401 if invalid), **stored in Postgres and answered 200 immediately**. The worker processes stored webhooks asynchronously, with the same retry policy as events. No handler does work inline. Topics:
  - `orders/create` (Purchase join).
  - `markets/create`, `markets/update`, `markets/delete`: re-fetch Markets and flag new ones unmapped. A deleted Market's mapping is removed.
  - `app/uninstalled`, `app/scopes_update`.
  - The three compliance topics (§7).
  - Embed status is polled on app open, since no webhook reports it.
- **Billing:** Shopify App Pricing, with one plan defined in the Partner Dashboard.
  - The app knows only the **exact plan handle** and checks that the shop's subscription to it is active.
  - The app never holds amounts. There's no feature gating.
- **Protected customer data:** Level 2 for **email, phone, name, address**, declared in the Partner Dashboard before submission. They're used only for the Server Purchase.

## 6. Data model (Postgres, the app's own database and role)

| Table | Holds | Notes |
|---|---|---|
| `Session` | Shopify sessions | from the template |
| `Shop` | shop domain, storefront domain allowlist (re-fetched daily and on app open), embed status seen, verified-in-Meta flag, subscription status | replaces the POC's `ShopConfig` |
| `Market` | shop, numeric Market ID, name, type (Region / B2B / …), status (Active / Draft), first seen | the re-fetched Market list; "new" = no pixel and recently first seen |
| `MarketPixel` | shop, Market ID, pixel ID, pixel name, **encrypted** token, test event code, token state (ok / rejected) | the Pixel Mapping; the pair is mandatory |
| `AppKey` | Relay key pair, private key **encrypted** | generated once, republished on app start ([21](issues/21-security-and-operations.md)) |
| `Webhook` | shop, topic, Shopify webhook ID (deduplicates redeliveries), payload, status (received, processed, failed), attempts, next attempt, timestamps | the inbox for every webhook; `orders/create` payloads are hashed or deleted once processed; deleted after 30 days |
| `Event` | shop, source (Relay / webhook), event name, event ID, Market ID, pixel ID, consent, payload for Meta, status (received, sent, skipped, waiting, rejected, failed, paused), attempts, next attempt, Meta's answer, timestamps | the queue **and** the event log; holds no raw personal data; deleted after 30 days |
| `PendingPurchase` | shop, order ID, browser half, **hashed** order customer data | expires after 7 days; the POC's raw order JSON must not carry over |

Encryption at rest uses an AES-256-GCM helper modelled on AdFeed Studio's `packages/meta-connector/src/crypto.ts`, with this app's own key ([08](issues/08-afs-stack-reuse.md)).

## 7. Privacy and compliance ([13](issues/13-compliance-plan.md), [03](issues/03-app-store-requirements.md))

- **No raw personal data kept.** Event and pending Purchase data is hashed before storage. A stored `orders/create` webhook holds raw customer data only until the worker processes it; then it's hashed or deleted.
- **GDPR webhooks:** all verify the HMAC (401 on a bad one), are stored and answered 200, and the worker carries them out.
  - `customers/data_request`: log it and send the merchant a fixed reply (we hold nothing identifiable).
  - `customers/redact`: delete `Event` and `PendingPurchase` rows for the listed order IDs.
  - `shop/redact` (48 h after uninstall): delete everything for the shop.
- **Uninstall:** the worker deletes the shop's tokens as soon as it processes `app/uninstalled`, and stop accepting Relays for the shop. Everything else goes at `shop/redact`, inside the 30-day API Terms limit.
- **Privacy policy** on `adfeedstudio.com` (an entry in the website's apps data). It covers:
  - What's processed: IP, user agent, `_fbp`/`_fbc`, hashed contact and address data, order ID and value.
  - Purpose: sending conversions to the merchant's own pixels.
  - Meta as the only sub-processor, and the retention periods (7 and 30 days).
  - The merchant as controller and us as processor.
- **API Terms §2.3.19:** no prior consent sought ([16](issues/16-shopify-data-sharing-consent.md), [ADR 0003](../../docs/adr/0003-no-prior-shopify-consent-for-data-sharing.md)).
- **Listing:** English screencast, test credentials, 1200×1200 icon, prices only in the Pricing section.

## 8. Hosting and operations ([12](issues/12-hosting-data-secrets.md), [21](issues/21-security-and-operations.md))

- A Docker app (web + worker) on a VPS behind Caddy, one instance per app (UAT and Production).
- Postgres with the app's own database and role, possibly on an existing AFS Postgres server. Prisma migrations.
- The Relay key pair is generated once, stored encrypted and **republished automatically on app start** (metafield + Web Pixel settings).
- **Daily jobs:** re-fetch storefront domains and delete expired `PendingPurchase` rows and `Event` rows older than 30 days.
- **Backups:** a nightly Postgres dump, kept 14 days, stored off the VPS.
- Secrets (Shopify API secret, encryption key, database URL) come from the environment and are never committed.

## 9. Build and release

- Built **from scratch on a clean git branch**. The POC (`shopify-app/`) is a reference only ([18](issues/18-poc-code-reuse.md)).
- **Automated tests** ([19](issues/19-test-strategy.md)): Relay decryption and validation, the Purchase join, Meta payload building (`content_ids`, hashing), GDPR webhooks, worker retry and pause.
- **UAT App:** all other testing is manual, following a **release checklist** before every Production App release. The checklist includes:
  - Full Standard Funnel per Market.
  - Browser + server dedup in Events Manager.
  - Consent off → nothing sent.
  - Token rejection → paused, then resumed.
  - Adding a Market → shows as unmapped.
  - Uninstall cleanup.
  - The checks still open in §11.

## 10. Support ([22](issues/22-support-and-docs.md))

English help pages on `adfeedstudio.com`:
- A setup guide.
- Checking events in Events Manager.
- An FAQ, including that sharing a pixel with the Official Meta App double counts ([07](issues/07-official-meta-app-coexistence.md)).

Support is by email, linked from the setup strip.

## 11. Known risks and checks for UAT

- Liquid `localization.market` is deprecated with no replacement ([ADR 0001](../../docs/adr/0001-storefront-market-from-deprecated-liquid-localization-market.md)). Watch the changelog.
- App Review may raise API Terms §2.3.19 ([ADR 0003](../../docs/adr/0003-no-prior-shopify-consent-for-data-sharing.md)).
- To check on the UAT App:
  - Whether B2B buyers get the same Market on the storefront and at checkout.
  - Whether `markets/update` fires on condition or status changes.
  - Whether uninstalling removes the Web Pixel and the app-owned metafield automatically.
  - Whether an Events Manager token can read its own pixel (the "Check with Meta" call; if not, fall back to a test event).

## Decision index

All decisions, with their reasoning, are in the map's [Decisions so far](map.md#decisions-so-far).
