# Store every webhook, answer 200, and process it in the worker

Type: AFK
Status: open
Assignee:
Blocked by: 01
Spec: §3.2, §5, §6 (`Webhook`), §7
Backlog: [backlog.md](backlog.md)

## What

The generic path every webhook takes: verify the HMAC (401 if bad), insert into the `Webhook` table (deduplicated by Shopify's webhook ID), answer 200. The worker claims received rows, dispatches by topic, and retries with the event backoff (1 min, 5 min, 30 min, 2 h, 6 h), then marks the row failed. Implement the handlers that need nothing else: `app/uninstalled` (delete tokens, stop accepting Relays), `app/scopes_update`, and the compliance topics (`customers/data_request` logs + fixed reply, `customers/redact` deletes rows by order ID, `shop/redact` deletes everything for the shop). Declare `compliance_topics` in both configs.

## Acceptance criteria

- [ ] Every webhook route does nothing but verify, store, return 200
- [ ] A redelivered webhook (same ID) is stored once and processed once
- [ ] The worker retries a failing handler on the backoff schedule, then marks it failed
- [ ] Automated tests: HMAC rejection, dedup, GDPR redact handlers, uninstall token deletion
- [ ] Compliance webhooks registered and triggered successfully from the CLI on the UAT App
