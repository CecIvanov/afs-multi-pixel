# Can Meta's pixel run inside the Web Pixel sandbox and address several pixels?

Type: research
Label: wayfinder:research
Status: resolved
Map: [Multi-Pixel map](../map.md)

## Question

Shopify app Web Pixels run in a **strict sandbox** (a web worker with no DOM). Can Meta's pixel work there, and how do we send one event to one chosen pixel out of several?

- Can `fbevents.js` / `fbq` load in the strict sandbox? If not, what is Meta's documented way to send browser events without `fbq` (for example the `https://www.facebook.com/tr` image/beacon endpoint), and which parameters does it need (`id`, `ev`, `cd[...]`, `eid`, `fbp`/`fbc` cookies)?
- If `fbq` works: how do you send an event to one pixel only when several are initialised (`fbq('trackSingle', ...)`)?
- What happens to the `_fbp` / `_fbc` cookies and advanced matching when events are sent from the sandbox? Can a Shopify pixel read and write cookies through its `browser` API?
- How does Meta's own Shopify integration (the Official Meta App's pixel) send events today? This is prior art.

Answer with primary sources (developers.facebook.com Meta Pixel docs, shopify.dev Web Pixels sandbox docs).

## Answer

Findings: branch `research/meta-pixel-in-web-pixel-sandbox`, file `research/meta-pixel-in-web-pixel-sandbox.md`. The research used docs, public source code (fbevents.js, web-pixels-manager, the Official Meta App's pixel) and a curl test of `/tr`.

- **`fbq` can't run in our pixel.** App pixels are `strict` (a web worker with no `document`), and `fbevents.js` needs the DOM. `trackSingle` is only available where `fbq` loads.
- **Send events to the image-pixel endpoint instead:** `https://www.facebook.com/tr?id=<pixel>&ev=<event>&cd[...]`, plus `eid` (event id, for future CAPI dedup), `ud[...]` (hashed advanced matching) and `dpo*` (Limited Data Use). Each request names exactly one pixel, so routing to one Market Pixel needs nothing extra. `/tr` accepts a `fetch` from the sandbox (its CORS headers allow it).
- **Cookies:** the pixel can read and write the shop's first-party `_fbp` / `_fbc` through `browser.cookie`. Reuse them if present, or create them in Meta's format (`fb.1.<ms>.<random>`, and `fb.1.<ms>.<fbclid>` when the URL has `fbclid`).
- **Advanced matching** (email, phone, name, address) needs protected customer data approval. Without it those fields are null.
- **The Official Meta App** runs an `OPEN` (top-frame) pixel that loads the real `fbevents.js`. Third-party apps must be `strict`, so we can't copy it.
- **Recommended per event:** resolve the Market Pixel for the current Market, read or create `_fbp` / `_fbc`, then `fetch('https://www.facebook.com/tr/?id=<MarketPixel>&ev=<Event>&eid=<shopify event.id>&dl&rl&ts&fbp&fbc&cd[...]', {keepalive: true})`.
- **Needs confirming in Meta Test Events:** the parameters taken from `fbevents.js` behaviour rather than Meta's docs (`dl`, `ts`, `fbp` / `fbc` as query parameters, how `cd[content_ids]` is encoded). Match quality may be lower than the Official Meta App's, because Meta's own facebook.com cookie isn't sent.
