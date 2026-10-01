# AFS Multi Pixel: production app spec

Label: wayfinder:map
Status: closed (destination reached, 2026-10-01)

## Destination

A **build-ready spec for v1** of AFS Multi Pixel, the public Shopify App Store app: `.scratch/multi-pixel-app/spec.md`, written up as tickets close, plus ADRs in `docs/adr/` for the hard-to-reverse calls. It's done when every v1 area has a decision and nothing blocks a developer from starting. The areas are v1 scope, merchant UX, data model and hosting, the Meta integration, the Shopify integration (with compliance and App Store review), pricing and billing, the AFS relationship, test strategy, and POC code reuse. The user is the sole sign-off. Slicing the spec into implementation issues is a separate, later effort.

## Notes

- **Plan only.** Production code waits until the spec is done. `task` tickets only unblock decisions. Throwaway prototypes are fine where "how should it behave" is the question.
- **v1 horizon.** Specify only what ships first. Later items (other ad platforms, headless) appear only as constraints on naming and architecture.
- **v1 is English only** (admin UI and listing; the user, 2026-10-01).
- **Business is in scope**: AFS relationship, segment, pricing, positioning, and support plan as *decisions*. Writing marketing or help-center content is not.
- Brief: [brief.md](brief.md). POC map (closed, successful): [../multi-pixel/map.md](../multi-pixel/map.md). POC code: `shopify-app/` (run guide `shopify-app/POC.md`).
- Vocabulary: `/CONTEXT.md` (Market, Market Pixel, Pixel Mapping, Standard Funnel, Official Meta App, Browser Event, Server Event, Relay, Market Catalog). Use those terms.
- **Inherited from the POC; don't reopen without cause:**
  - Market detection: a theme app embed reads `localization.market.id` (cookie `_mpx_market`); checkout uses `checkout.localization.market.id`; numeric Market IDs.
  - Senders: the embed sends PageView, ViewContent and Search with `fbq trackSingle`; the strict Web Pixel sends AddToCart, InitiateCheckout, AddPaymentInfo and Purchase via `/tr`.
  - Event shape identical to the Official Meta App (product IDs, `content_type: product_group`).
  - Pixel Mapping semantics: 0 or 1 pixel per Market, shared pixels allowed, no fallback, the Market in effect when the event fires.
  - Encrypted Relay → Server Event with the same event ID; Purchase joined with `orders/create` on the order ID; no server Purchase without a browser Purchase.
  - Consent via the Customer Privacy API and the store's own banner; the app builds none.
- Skills: `grilling` + `domain-modeling` (default); `adfeedstudio:business-analyst` (requirements, personas); `adfeedstudio:sales` / `adfeedstudio:marketing` (pricing and positioning tickets); `research` for Shopify, Meta and competitor facts. The AFS code is local: `~/Projects/adfeedstudio-saas`, `adfeedstudio-saas-portal`, `adfeedstudio-lb`.
- POC research branches worth reusing: `research/market-detection-in-web-pixel`, `research/meta-pixel-in-web-pixel-sandbox`, `research/thank-you-page-fallback`, `research/capi-and-content-ids`.
- Tracker: local markdown. Tickets are in `issues/` (`Blocked by:` lists ticket numbers; a claim is `Assignee:`). Research findings go in `research/<name>.md` on `research/<name>` branches.

## Decisions so far

<!-- one line per closed ticket: [title](issues/NN-slug.md): gist -->

- **Spec signed off (2026-10-01, the user's call):** [spec.md](spec.md) is the build-ready v1 spec, with ADRs 0001–0003 in `/docs/adr`. This map is closed. Slicing the spec into implementation issues is the next, separate effort.
- [What in the AdFeed Studio stack could AFS Multi Pixel reuse?](issues/08-afs-stack-reuse.md): reuse VPS-Black + Caddy hosting, the Postgres server (own database), the AES-GCM helper and the website's privacy/listing pages. Don't reuse Stripe billing (App Store forbids it), SaaS accounts, or the AFS Meta app (pending review).
- [What do existing multi-pixel and Conversions API apps on the Shopify App Store offer and charge?](issues/05-competitors.md): per-Market routing exists only as a top tier (Omega), a bundle (WeltPixel $39) or enterprise (Elevar). Plain multi-pixel apps cost $5–$49/mo and set up by manual token. Our opening: Market routing as the core product, Official-Meta-App-matching event shape, and AFS catalog fit.
- [How does an app follow a store's Markets over time and detect that its theme app embed is on?](issues/06-markets-lifecycle-and-embed.md): `markets/create|update|delete` webhooks (numeric id only; no merge or hierarchy webhook) → re-fetch. Embed status via `app.extensions()` in the admin or `settings_data.json` with `read_themes`; there's an activation deep link; `themes/publish` fires, but embed toggles must be polled. ⚠ Liquid `localization.market` is deprecated ("Market IDs no longer stable"), so it gets its own ticket.
- [Can the Official Meta App run alongside us without double counting, and can we detect it?](issues/07-official-meta-app-coexistence.md): yes, if the channel's data sharing is off (catalog and Shops appear unaffected, unverified) or our Market Pixels differ from its pixel. A shared pixel double counts (Meta dedups only browser↔server on the same event ID). We can't see the channel's pixel and can at best detect that it's installed.
- [How can a third-party app connect a merchant's Meta account to list pixels and obtain Conversions API tokens?](issues/04-meta-connection-options.md): Facebook Login for Business (CAPI partner template) gives one non-expiring business token and the pixel list, but gates on App Review, Business Verification and Tech Provider (weeks). Manual entry can be validated with `GET /<pixel>`. There's no disconnect webhook.
- [What does the Shopify App Store require of a public pixel + Conversions API app?](issues/03-app-store-requirements.md): mandatory GDPR webhooks; Level 2 protected-data review per field (unapproved fields are null in webhooks and Web Pixel events); Shopify billing mandatory (Shopify App Pricing default); BFS badge optional, but its rule 5.1.1 and Lighthouse budget pressure the `fbevents.js` embed. ⚠ API Terms §2.3.19 ("primary purpose" data sharing needs Shopify consent) gets its own task ticket.
- [How does the merchant connect Meta in v1: Meta login or validated manual entry?](issues/10-meta-connection-method.md): manual entry. Pixel ID + CAPI token is a mandatory pair per mapped Market; no Meta login in v1.
- [Does Shopify consider AFS Multi Pixel's Conversions API relay "primary purpose" data sharing under API Terms §2.3.19?](issues/16-shopify-data-sharing-consent.md): not pursued. The merchant supplies their own pixel + token, so the app acts on their instruction; we handle it if App Review raises it.
- [Is AFS Multi Pixel a standalone App Store product, an add-on bundled with AdFeed Studio, or a funnel into AFS?](issues/01-afs-relationship.md): standalone. Own listing, Shopify-session accounts, Shopify billing, no AFS account link in v1.
- [Which merchants is v1 for, and in which languages?](issues/02-target-merchants.md): any Online Store merchant with 2+ Markets, English only; no segment-specific features.
- [What does a paid app do about the Official Meta App sending to the same pixels?](issues/11-official-meta-app-conflict-policy.md): nothing. Reusing its pixel is the merchant's configuration choice; no detection or warning.
- [What happens to storefront Market detection when Liquid `localization.market` is deprecated or Market IDs shift?](issues/15-market-id-stability.md): ship on `localization.market` as a watched dependency; flag new Markets without a pixel as "unmapped" in the admin; no parent → child pixel inheritance.
- [Which customer data does v1 request, and how does it meet App Store and GDPR obligations?](issues/13-compliance-plan.md): Level 2 email/phone/name/address for the server Purchase only (hashed), no browser PII; no raw PII stored (7-day pending Purchase, 30-day log); GDPR webhooks and uninstall deletion defined; consent gates `fbevents.js`; no BFS badge in v1; privacy policy on `adfeedstudio.com`.
- [How is AFS Multi Pixel priced and billed?](issues/09-pricing-and-billing.md): Shopify App Pricing. Shopify defines and charges the plans; the app knows only the exact plan handle, never amounts. One paid plan, no trial, no feature gating.
- [Where does production run, and how are its data and secrets stored?](issues/12-hosting-data-secrets.md): a Docker app on a VPS with Postgres (own database, Prisma migrations), single instance, tokens encrypted at rest.
- [How does the merchant set up and maintain their Pixel Mapping in the admin?](issues/14-onboarding-and-mapping-ux.md): variant C, "Market health". The home page is the Markets page: one tile per Market (health, pixel, 24 h chart, counts), dashed tiles for unmapped Markets, a setup strip until done, a modal for the pixel + token pair, and an event log drawer. Prototype on branch `prototype/admin-ux`.
- [How does the single-instance backend send Server Events reliably?](issues/17-relay-reliability.md): store every Relay event and every Shopify webhook in Postgres first (webhooks answered 200 at once), then a worker processes them asynchronously. Backoff retries for about 9 h, then failed; a rejected token pauses the Market; daily cleanup; per-shop/IP rate limits.
- [Is the POC's `shopify-app/` the base for production, or only a reference?](issues/18-poc-code-reuse.md): reference only. Start clean on a new branch. Two apps from one codebase: the UAT App (custom, test stores) and the Production App (public listing).
- [What is the v1 test strategy?](issues/19-test-strategy.md): automated tests for Relay, Purchase join, payload building, GDPR webhooks and worker retries; everything else by hand on the UAT App with a release checklist.
- [How does v1 behave for B2B Markets, shared domains, and a storefront and checkout that disagree on the Market?](issues/20-market-edge-cases.md): no special logic. Events follow the Market Shopify reports; B2B and Draft Markets are ordinary tiles; B2B consistency is checked on UAT.
- [How are the Relay key, Origin checks and backups handled in production?](issues/21-security-and-operations.md): the key is stored encrypted and republished on app start; Origin allowlist re-fetched daily and on app open; nightly off-VPS Postgres dump kept 14 days.
- [What support and documentation does v1 ship with?](issues/22-support-and-docs.md): English help pages on `adfeedstudio.com` (setup guide, Events Manager check, FAQ) plus email support, linked from the setup strip.

## Not yet specified

Nothing. The way to the destination is clear.

## Out of scope

- **Creating or syncing per-market catalogs**: AFS's or the merchant's job. The app only sends matching `content_ids`.
- **Headless / Hydrogen storefronts**: Online Store themes only.
- **Other ad platforms (TikTok, Google) in v1**: carried only as a naming and architecture constraint.
- **Writing help-center or marketing content**: the spec records the decisions, not the copy.
