# Is the POC's `shopify-app/` the base for production, or only a reference?

Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: Tsvetan Ivanov
Map: [AFS Multi Pixel map](../map.md)

## Question

Production keeps the POC's stack (React Router template, Node/TypeScript, Prisma, Docker) but swaps SQLite for Postgres, adds GDPR webhooks, Shopify App Pricing plan checks, token encryption, unmapped-Market handling and a new admin UI. Do we evolve `shopify-app/` in place (and in this repo), or start a fresh app and port the proven pieces (theme embed, Web Pixel, Relay crypto, Purchase join)? Consider the app's Shopify identity (`shopify.app.toml`, client ID, extensions' handles): is the POC's custom-distribution app the one that gets listed, or a new public app?

## Answer

**The POC is a reference only (the user's call, 2026-10-01).** Production starts from scratch on a **clean git branch**; proven pieces (theme embed, Web Pixel, Relay crypto, Purchase join) are rewritten from the POC as reference, not carried over.

**Two Shopify apps from the same code:**
- **UAT App:** a custom-distribution app, installed on test stores. All testing happens here.
- **Production App:** the public App Store app merchants install.

Each has its own app config, client ID and deployment.
