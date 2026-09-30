# Where does the Pixel Mapping live, and how does the storefront pixel read it?

Type: grilling
Label: wayfinder:grilling
Status: open
Blocked by: 01, 02, 07
Map: [Multi-Pixel map](../map.md)

## Question

The merchant edits the Pixel Mapping in the admin, and the storefront pixel has to resolve Market → Market Pixel on every event. Where is the source of truth, and how does it reach the pixel?

Candidates:
- Web Pixel extension **settings**, written through `webPixelCreate`/`webPixelUpdate` and passed to the pixel as `init.settings`.
- Postgres only, with the pixel fetching the mapping at runtime.
- Postgres as the source of truth, mirrored into pixel settings or an app-owned metafield on every change.

This hangs on what Market key the pixel can see (ticket 01) and how events get sent (ticket 02).
