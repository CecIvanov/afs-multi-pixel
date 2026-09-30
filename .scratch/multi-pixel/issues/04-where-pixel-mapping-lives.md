# Where does the Pixel Mapping live, and how does the storefront pixel read it?

Type: grilling
Label: wayfinder:grilling
Status: resolved
Blocked by: 01, 02, 07
Map: [Multi-Pixel map](../map.md)

## Question

The merchant edits the Pixel Mapping in the admin, and the storefront pixel has to resolve Market → Market Pixel on every event. Where is the source of truth, and how does it reach the pixel?

Candidates:
- Web Pixel extension **settings**, written through `webPixelCreate`/`webPixelUpdate` and passed to the pixel as `init.settings`.
- Postgres only, with the pixel fetching the mapping at runtime.
- Postgres as the source of truth, mirrored into pixel settings or an app-owned metafield on every change.

This hangs on what Market key the pixel can see (ticket 01) and how events get sent (ticket 02).

## Answer

Decided by the user on 2026-09-30: the backend stores the mapping (and the shop token) in **SQLite** through Prisma (`MarketPixel` table; the token is in the template's `Session` table). On save, `app/models/market-pixels.server.ts` mirrors `{ "<numeric market id>": "<pixel id>" }` to:
- an app-owned `json` metafield `multi_pixel.mapping` on the app installation, which the theme embed reads as `app.metafields.multi_pixel.mapping`;
- the Web Pixel's `settings.mapping` (`webPixelCreate` / `webPixelUpdate`), which checkout events read.

Markets are keyed by the numeric id, because Liquid gives a number and the Admin API and checkout give a `gid://shopify/Market/<n>`.
