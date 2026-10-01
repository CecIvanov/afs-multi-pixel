# What is the v1 test strategy?

Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: Tsvetan Ivanov
Blocked by: 18
Map: [AFS Multi Pixel map](../map.md)

## Question

The POC has no automated tests. For v1, what do we test and how: the Liquid theme embed, the strict Web Pixel (sandboxed, no `fbq`), Relay encryption and validation, the Purchase join with `orders/create`, GDPR webhooks, plan-handle gating; unit vs integration vs end-to-end on a dev store; and what manual verification (Events Manager dedup) remains before each release?

**Settled (the user, 2026-10-01):** all testing is done on the UAT App (custom distribution, test stores), never on the Production App. Open: whether automated tests exist alongside UAT testing, and what they cover.

## Answer

Agreed with the user, 2026-10-01.
- **Automated tests, small and targeted**, for the logic that's easy to get wrong and hard to see on UAT: Relay decryption and validation, the Purchase join with `orders/create`, Meta payload building (`content_ids`, hashing), GDPR webhooks, and worker retries.
- **Manual on the UAT App** for everything else (theme embed, Web Pixel, Events Manager dedup), following a release checklist before each Production App release.
