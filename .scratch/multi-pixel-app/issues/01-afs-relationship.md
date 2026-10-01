# Is AFS Multi Pixel a standalone App Store product, an add-on bundled with AdFeed Studio, or a funnel into AFS?

Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: Tsvetan Ivanov
Map: [AFS Multi Pixel map](../map.md)

## Question

How does AFS Multi Pixel relate to AdFeed Studio commercially and technically? Options: a standalone App Store product with its own accounts and billing; an add-on bundled with an AFS plan; or a free/cheap funnel that leads merchants into AFS. Decide which, and what that means for merchant accounts (Shopify-session only vs linked AFS account), billing ownership, onboarding entry point, and positioning. Consult `adfeedstudio:business-analyst` and `adfeedstudio:sales`.

## Answer

**Standalone App Store product (the user's call, 2026-10-01).** AFS Multi Pixel has its own listing, is installed and used on its own, and needs no AdFeed Studio account. With [What in the AdFeed Studio stack could AFS Multi Pixel reuse?](08-afs-stack-reuse.md), that means:
- **Accounts:** Shopify shop session only; no AFS org link in v1.
- **Billing:** through Shopify (App Store rule), set by the pricing ticket.
- **Branding and hosting:** "AFS" stays in the name and it's hosted under `adfeedstudio.com`. Infrastructure reuse (VPS, Postgres server, website pages) is an operations choice, not a product coupling.
