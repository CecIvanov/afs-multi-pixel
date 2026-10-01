# Which customer data does v1 request, and how does it meet App Store and GDPR obligations?

Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: Tsvetan Ivanov
Blocked by: 03
Map: [AFS Multi Pixel map](../map.md)

## Question

Given the App Store research: which protected customer data fields does v1 request (and so whether browser-side advanced matching with hashed email/phone is in v1), the GDPR webhook behaviour (`customers/data_request`, `customers/redact`, `shop/redact`), uninstall cleanup (metafield, web pixel, tokens, logs), data retention, and what the privacy policy and data processing statement must say.

Also: whether v1 aims for the Built for Shopify badge, given the 10-point Lighthouse budget and rule 5.1.1 (ads apps use Web Pixels, not script tags) against the theme embed loading `fbevents.js`.

## Answer

Agreed with the user, 2026-10-01 (sources: [What does the Shopify App Store require of a public pixel + Conversions API app?](03-app-store-requirements.md)).

- **Protected customer data:** request Level 2 **email, phone, name, address**, used only for the server Purchase and hashed before sending, as the POC does. Declare them in the Partner Dashboard before submission. **No browser-side advanced matching in v1** (no customer data in Browser Events).
- **Storage: no raw personal data.** The pending Purchase record (`PendingPurchase`) holds hashed values only and expires after **7 days**. The event log (`EventLog`) holds no personal data (event, Market, pixel, status, Meta's reply) and is kept **30 days**. Conversions API tokens are encrypted at rest (the AFS AES-GCM helper).
- **GDPR webhooks** (`compliance_topics` in the toml):
  - `customers/data_request`: log the request and send the merchant a fixed reply (we hold nothing identifiable).
  - `customers/redact`: delete pending Purchase and event-log rows for the listed order IDs.
  - `shop/redact`: delete everything for the shop.
  - All of them verify the HMAC (401 on a bad one) and return 2xx.
- **Uninstall** (`app/uninstalled`): delete Conversions API tokens immediately and stop accepting Relays for the shop. The mapping and logs go with `shop/redact` (48 h, inside the 30-day API Terms limit). Whether Shopify removes the Web Pixel and the app-owned metafield automatically must be checked on a test store.
- **Consent:** no Browser or Server Event without marketing consent. The theme embed loads `fbevents.js` only when `customerPrivacy.marketingAllowed()` **and** `saleOfDataAllowed()` are true.
- **Built for Shopify:** not targeted in v1 (rule 5.1.1 and the Lighthouse budget conflict with the `fbevents.js` embed). Revisit after launch.
- **Privacy policy** on `adfeedstudio.com` (website apps page). It covers:
  - Data processed: IP, user agent, `_fbp`/`_fbc`, hashed contact and address data, order ID and value.
  - Purpose: conversions to the merchant's own pixels.
  - Meta as the only sub-processor, and the retention periods above.
  - The merchant as controller and us as processor.
