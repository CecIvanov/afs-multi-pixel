# Which identifier goes into content_ids so events match the merchant's catalogs?

Type: grilling
Label: wayfinder:grilling
Status: resolved
Blocked by: 01
Map: [Multi-Pixel map](../map.md)

## Question

Meta matches pixel events to catalog items through `content_ids`. Each Market's catalog is built outside the app (for example by the Official Meta App's catalog sync, AdFeed Studio, or a feed app), so what should the app send: the Shopify product id, the variant id, the SKU, or the `shopify_<country>_<product>_<variant>` format the Official Meta App uses? Should it be a per-store setting?

This hangs on which identifiers the Web Pixel payloads carry (ticket 01).

## Notes

The POC currently sends Shopify **product** ids as `content_ids` with `content_type: product_group` (both extensions). The decision stays open until it's checked against how the merchant's per-Market catalogs are keyed.

## Answer

Resolved on 2026-10-01 with the user. Events must match the Official Meta App. Observed live on colourpop.com (a store running the Facebook & Instagram channel): `content_ids` = Shopify **product** IDs with `content_type: product_group` on ViewContent, AddToCart and InitiateCheckout (and Purchase, per its source code); `content_name`, `content_category` (product type), `value` (AddToCart: unit price; checkout: total), `currency`, `num_items`; `eid` = Shopify event ID.

AdFeed Studio Market Catalogs use `id` = variant ID and `item_group_id` = product ID (checked in a real feed), so `product_group` + product IDs matches them. Meta's docs advise against `product_group` on AddToCart and Purchase; the user chose to stay identical to the Official Meta App.
