# What does the Shopify App Store require of a public pixel + Conversions API app?

Type: research
Label: wayfinder:research
Status: resolved
Assignee: Tsvetan Ivanov (research subagent)
Map: [AFS Multi Pixel map](../map.md)

## Question

From primary sources (shopify.dev, App Store requirements, Built for Shopify criteria, changelog): listing requirements; the mandatory GDPR webhooks and their expected behaviour; protected customer data levels, what each field (name, email, phone, address from `orders/create`) needs, and how the review works and how long it takes; Built for Shopify performance rules that apply to a theme app embed loading Meta's `fbevents.js`; Billing API rules for charging apps (must we use it, trials, usage charges); uninstall expectations; any rules specific to pixel/tracking apps or apps that send data to third parties.

## Answer

Findings: branch `research/app-store-requirements`, file `research/app-store-requirements.md`.

- **⚠ Highest risk, API Terms §2.3.19:** apps whose "primary purpose" is passing Merchant Data to a third party need Shopify's prior written consent. Whether a Meta CAPI relay counts is unclear. Graduated into [Does Shopify consider AFS Multi Pixel's Conversions API relay "primary purpose" data sharing under API Terms §2.3.19?](16-shopify-data-sharing-consent.md). The terms also require the Customer Privacy API (§2.3.21), deleting Merchant Data within 30 days of uninstall (§6.2.3), and reporting a breach within 24 h (§6.2.10).
- **GDPR webhooks** (`customers/data_request`, `customers/redact`, `shop/redact`) are mandatory, or the app is rejected: 2xx, 401 on a bad HMAC, act within 30 days; `shop/redact` arrives 48 h after uninstall. The POC toml has no `compliance_topics`.
- **Protected customer data:** name, email, phone and address mean Level 2, requested and justified per field and reviewed with the app (request before submitting). Unapproved fields come back null, in webhooks and, since 2025-12-10, in Web Pixel events too.
- **Billing:** charging through Shopify is mandatory, and Shopify App Pricing is the default for new apps. Trials are tracked over 180 days (reinstalling doesn't reset them). Usage charges go through the App Events API, monthly only, no caps, no PII.
- **Built for Shopify (optional badge):**
  - At most a 10-point Lighthouse cost (Home 17%, Product 40%, Collection 43%, mobile), and ~10 KB of compressed JS suggested.
  - Rule 5.1.1: ads apps must use Web Pixels, not script tags. This is in tension with the embed loading `fbevents.js`.
- **Consent:** the embed must gate `fbevents.js` itself with `customerPrivacy.marketingAllowed()` / `saleOfDataAllowed()`. That Server Events must follow consent is inferred, not stated.
- **Listing:** privacy policy, English screencast, working test credentials, 1200×1200 icon, prices only in the Pricing section. Review time is unofficial: 5–10 business days per community reports.
- **Uncertain:** §2.3.19's reach; whether a BFS audit accepts the `fbevents.js` embed; whether the web pixel is removed automatically on uninstall.
