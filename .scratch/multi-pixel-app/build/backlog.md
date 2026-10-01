# AFS Multi Pixel v1: build backlog

Sliced from the signed-off [spec](../spec.md) (2026-10-01). Each ticket is a thin end-to-end slice that can be tested on the UAT App. Tracker: local markdown, same conventions as the map (claim with `Assignee:`, `Blocked by:` lists ticket numbers). Work happens on branch `production`, which starts from the user's ShopifyAppTemplate (commit `c3265d2`); the POC (`shopify-app/` on master) is reference only. Tickets 01, 02 and 09 are mostly covered by the template; see their re-scope notes.

**Rules every ticket follows** (from the spec): every Relay event and every webhook is stored in Postgres first and processed by the worker; no raw personal data is kept; tokens and keys are encrypted at rest; all testing on the UAT App; secrets never in git.

| # | Ticket | Blocked by |
|---|---|---|
| [00](00-partner-dashboard-setup.md) | Set up the UAT App, the Production App, protected data access and the plan | — |
| [01](01-app-foundation.md) | Start the production app on a clean branch with Postgres, Docker and two app configs | — |
| [02](02-webhook-inbox.md) | Store every webhook, answer 200, and process it in the worker | 01 |
| [03](03-markets-and-mapping.md) | Sync Markets and let the merchant map pixel + token pairs on the Market health page | 01, 02 |
| [04](04-publish-mapping-and-keys.md) | Publish the Pixel Mapping, Relay key and endpoint to the storefront and checkout | 03 |
| [05](05-theme-embed.md) | Send storefront events from the theme app embed, gated by consent | 04 |
| [06](06-checkout-web-pixel.md) | Send AddToCart and checkout events from the strict Web Pixel | 04 |
| [07](07-server-events.md) | Store Relays and send Server Events to the Conversions API from the worker | 02, 05, 06 |
| [08](08-purchase-join.md) | Join the browser Purchase with orders/create and send the hashed Server Purchase | 07 |
| [09](09-billing-check.md) | Require the active subscription to the one paid plan | 01, 00 |
| [10](10-operations.md) | Add daily jobs, backups and the UAT release checklist | 07, 08 |
| [11](11-app-store-submission.md) | Prepare and submit the Production App to the App Store | 00, 10 |

Order of work: 01 → 02 → 03 → 04 → (05 and 06 in parallel) → 07 → 08 → 10 → 11. 00 (the user) runs in parallel from now; 09 only needs 01 and the plan handle from 00.
