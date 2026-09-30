# Can Meta's pixel run inside the Web Pixel sandbox and address several pixels?

Type: research
Label: wayfinder:research
Status: open
Map: [Multi-Pixel map](../map.md)

## Question

Shopify app Web Pixels run in a **strict sandbox** (a web worker with no DOM). Can Meta's pixel work there, and how do we send one event to one chosen pixel out of several?

- Can `fbevents.js` / `fbq` load in the strict sandbox? If not, what is Meta's documented way to send browser events without `fbq` (for example the `https://www.facebook.com/tr` image/beacon endpoint), and which parameters does it need (`id`, `ev`, `cd[...]`, `eid`, `fbp`/`fbc` cookies)?
- If `fbq` works: how do you send an event to one pixel only when several are initialised (`fbq('trackSingle', ...)`)?
- What happens to the `_fbp` / `_fbc` cookies and advanced matching when events are sent from the sandbox? Can a Shopify pixel read and write cookies through its `browser` API?
- How does Meta's own Shopify integration (the Official Meta App's pixel) send events today? This is prior art.

Answer with primary sources (developers.facebook.com Meta Pixel docs, shopify.dev Web Pixels sandbox docs).
