# How does v1 behave for B2B Markets, shared domains, and a storefront and checkout that disagree on the Market?

Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: Tsvetan Ivanov
Map: [AFS Multi Pixel map](../map.md)

## Question

Graduated from the map's fog: B2B Markets, a domain or subfolder shared by several Markets, and the storefront and checkout choosing different Markets.

## Answer

**No special logic (agreed with the user, 2026-10-01).** Each event goes to the Market Shopify reports when it fires: the embed's `localization.market` on the storefront and `checkout.localization.market` at checkout. A journey that changes Market splits across pixels (inherited rule). Shared domains need nothing extra, because Shopify resolves the Market. B2B and Draft Markets are ordinary tiles and can be given a pixel. Whether B2B buyers get the same Market on the storefront and at checkout is checked on the UAT App during the build, as a release-checklist item, not a spec rule.
