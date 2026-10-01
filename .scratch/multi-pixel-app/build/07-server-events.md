# Store Relays and send Server Events to the Conversions API from the worker

Type: AFK
Status: open
Assignee:
Blocked by: 02, 05, 06
Spec: §3.2, §4 (summary, tiles, event log), §6 (`Event`)
Backlog: [backlog.md](backlog.md)

## What

`POST /api/events`: decrypt, validate (Origin in allowlist, known shop, market → pixel in mapping, rate limits per shop and IP), store an `Event` row, answer. The worker sends to `graph.facebook.com/v26.0/<pixel>/events` (same event ID, IP, UA, fbp/fbc, token, test event code), retries on the backoff, marks failed after the last attempt, and on a rejected token pauses that Market's server events (tile shows Token problem; resumes and sends events under 7 days old once the token is replaced). Fill the summary row, tile counts, 24 h chart and the event log drawer.

## Acceptance criteria

- [ ] Events Manager shows browser + server events deduplicated for each Market Pixel on the UAT store
- [ ] Killing Meta access (bad network or invalid token) loses no event: they're retried or paused, then sent
- [ ] Foreign Origin, unknown shop and unmapped pair are rejected and logged
- [ ] Automated tests: decryption/validation, retry schedule, pause and resume
- [ ] Tiles, summary and event log show real numbers
