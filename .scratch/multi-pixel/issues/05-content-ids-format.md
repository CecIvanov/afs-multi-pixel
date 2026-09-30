# Which identifier goes into content_ids so events match the merchant's catalogs?

Type: grilling
Label: wayfinder:grilling
Status: open
Blocked by: 01
Map: [Multi-Pixel map](../map.md)

## Question

Meta matches pixel events to catalog items through `content_ids`. Each Market's catalog is built outside the app (for example by the Official Meta App's catalog sync, AdFeed Studio, or a feed app), so what should the app send: the Shopify product id, the variant id, the SKU, or the `shopify_<country>_<product>_<variant>` format the Official Meta App uses? Should it be a per-store setting?

This hangs on which identifiers the Web Pixel payloads carry (ticket 01).
