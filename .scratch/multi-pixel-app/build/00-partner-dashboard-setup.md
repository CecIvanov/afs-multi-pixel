# Set up the UAT App, the Production App, protected data access and the plan

Type: task (HITL, the user)
Status: open
Assignee:
Spec: §1, §5, §7, §8
Backlog: [backlog.md](backlog.md)

## What

Shopify-side setup only the user can do. It runs in parallel with the build; only the items that need its outputs wait for it.

Checklist (verify each screen as you go; Shopify moves these menus around):
1. **UAT App:** once ticket 01 has created the clean branch, run (in it) `shopify app config link`, choose *Create a new app*, name it "AFS Multi Pixel UAT", and save the config as `uat` (gives `shopify.app.uat.toml`). In the Partner Dashboard, set its distribution to **Custom distribution** and generate an install link for each test store (start with `gpay3y-2v.myshopify.com`).
2. **Production App:** the same with the name "AFS Multi Pixel" and the config `production` (`shopify.app.production.toml`). Set its distribution to **Public distribution** (App Store). This is permanent.
3. **Protected customer data (Production App, and UAT for testing):** App → API access → Protected customer data → request access. Reason: conversion tracking / ads measurement. Level 2 fields: **name, email, phone, address**. Justification: "Hashed (SHA-256) and sent only with the Purchase event to the merchant's own Meta pixel via the Conversions API, after the shopper gave marketing consent; never stored in raw form." Do this now; it can't be requested during app review.
4. **Plan:** Production App → Distribution / listing → Pricing → **Managed pricing (Shopify App Pricing)** → one recurring plan, **no trial**. Write down the plan's **exact handle** as Shopify shows it (if the screen shows no handle, record the plan name exactly and say so; the billing ticket will confirm how the API reports it).
5. **Hosting decision:** which VPS and Postgres server UAT and Production run on, and their domains (for example `multi-pixel-uat.adfeedstudio.com`, `multi-pixel.adfeedstudio.com`).
6. Put the client IDs, plan handle and domains in this ticket. **Never paste client secrets here or anywhere in git**; they go only into the VPS `.env` files.

## Acceptance criteria

- [ ] UAT App created (custom distribution), client ID recorded here
- [ ] Production App created (public distribution), client ID recorded here
- [ ] Protected customer data (Level 2: name, email, phone, address) requested; request status recorded
- [ ] One paid plan, no trial, in managed pricing; exact plan handle recorded
- [ ] VPS, Postgres server and domains for UAT and Production recorded
