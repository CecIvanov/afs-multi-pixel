# Does Shopify consider AFS Multi Pixel's Conversions API relay "primary purpose" data sharing under API Terms §2.3.19?

Type: task
Label: wayfinder:task
Status: resolved
Assignee: Tsvetan Ivanov
Map: [AFS Multi Pixel map](../map.md)

## Question

Shopify API Terms §2.3.19 bars apps whose "primary purpose" is passing Merchant Data to a third party unless Shopify gives prior written consent (see [What does the Shopify App Store require of a public pixel + Conversions API app?](03-app-store-requirements.md)). AFS Multi Pixel's core job is sending Browser and Server Events, including hashed customer data from `orders/create`, to Meta. Many listed CAPI apps exist, so there's likely a sanctioned path, but it must be confirmed before the compliance plan and v1 scope are fixed.

HITL: the user asks Shopify Partner Support, describing the app (per-Market Meta pixel routing, browser + Conversions API, consent-gated, hashed PII on Purchase), and asks: does §2.3.19 apply; if so, how do we obtain consent; does it change if we drop hashed PII; and does a Built for Shopify review accept a theme app embed that loads `fbevents.js` (rule 5.1.1)? Record the answer and any written consent on this ticket.

## Answer

**Not pursued (the user's call, 2026-10-01).** No explicit §2.3.19 consent is sought from Shopify. The merchant supplies their own pixel ID and Conversions API token per Market, so the merchant directs where their data goes, and the app acts on their instruction. The residual risk is that App Review raises it; we handle it then. The Built for Shopify question about the `fbevents.js` embed stays in the compliance plan ticket.
