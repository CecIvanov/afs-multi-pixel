# How is AFS Multi Pixel priced and billed?

Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: Tsvetan Ivanov
Blocked by: 01, 03, 05
Map: [AFS Multi Pixel map](../map.md)

## Question

Pricing model (free, flat fee, per Market Pixel, per event volume, tiers), trial, price points, and billing channel (Shopify Billing API vs AFS billing, within App Store rules). Consult `adfeedstudio:sales` and `adfeedstudio:marketing`.

## Answer

**Shopify bills; the app only knows plan handles (the user's call, 2026-10-01).** AFS Multi Pixel is listed on the App Store and uses Shopify App Pricing: plans, prices and trials are defined in the Partner Dashboard and Shopify charges the merchant. Amounts are unknown to the app and never hard-coded. The app's only billing knowledge is the **exact subscription plan handles**, used to read the shop's active plan. Price points and the plan line-up are listing decisions made in the Partner Dashboard, outside the spec.

**One paid plan, no trial (the user, 2026-10-01).** There's no feature gating by plan: the app only checks that the shop's subscription to that one plan handle is active.
