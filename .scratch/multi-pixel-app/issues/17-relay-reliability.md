# How does the single-instance backend send Server Events reliably?

Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: Tsvetan Ivanov
Map: [AFS Multi Pixel map](../map.md)

## Question

With one Docker instance and Postgres ([Where does production run, and how are its data and secrets stored?](12-hosting-data-secrets.md)): does v1 keep the POC's synchronous send per Relay, or queue Server Events in Postgres with a worker (retries with backoff, Meta rate-limit and 5xx handling, dead letters)? How are failures surfaced to the merchant (event log statuses, a broken-token state)? What's the cleanup job for the 7-day pending Purchase expiry and the 30-day event log? What event volume per shop do we design for (no segment was chosen)? And what per-shop/IP rate limits does the Relay endpoint apply?

## Answer

**Store first, then send asynchronously (the user's call, 2026-10-01).** The Relay endpoint (and the `orders/create` webhook) only validates the event and **stores it in Postgres**, then answers. A **worker** picks stored events up and sends them to Meta's Conversions API asynchronously, so nothing is lost if Meta is slow or down or the app restarts. The event row is the source of truth for the event log.

Details still to settle (retry and backoff policy, when an event is marked failed, how a rejected token pauses a Market, cleanup jobs for the 7-day pending Purchase and the 30-day log, rate limits on the Relay endpoint) are in the map's fog as "Worker and Relay details".

**Worker details (agreed with the user, 2026-10-01):**
- **Retries** back off at 1 min, 5 min, 30 min, 2 h and 6 h, then the event is marked **failed** and shown in the event log (well inside Meta's 7-day event age limit).
- **Rejected token:** the worker pauses that Market's server events. They stay stored and are sent once the token is fixed, if still under 7 days old. The Market tile shows "Token problem", and browser events continue.
- **Cleanup:** a daily job deletes pending Purchases older than 7 days and events older than 30 days.
- **Rate limits:** the Relay endpoint is limited per shop and per IP; the numbers are set during the build.

**All Shopify webhooks too (the user, 2026-10-01):** every webhook (`orders/create`, `markets/*`, `app/*`, the compliance topics) is verified (HMAC; 401 if bad), **stored in Postgres and answered 200 immediately**. A worker then processes it asynchronously. No webhook handler does its work inline.
