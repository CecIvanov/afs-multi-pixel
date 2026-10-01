# How are the Relay key, Origin checks and backups handled in production?

Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: Tsvetan Ivanov
Map: [AFS Multi Pixel map](../map.md)

## Question

Graduated from the map's fog: relay key rotation without "save again after deploy", Origin checks once custom domains are added, and backups.

## Answer

Agreed with the user, 2026-10-01.
- **Relay key pair:** generated once, stored encrypted in Postgres, and republished automatically to the shop's metafield and Web Pixel settings on app start. No manual "save again after deploy".
- **Origin check:** the Relay accepts events only from the shop's own storefront domains. The domain list is re-fetched from Shopify daily and whenever the merchant opens the app.
- **Backups:** a nightly Postgres dump, kept 14 days, stored off the VPS.
