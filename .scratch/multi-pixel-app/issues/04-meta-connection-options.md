# How can a third-party app connect a merchant's Meta account to list pixels and obtain Conversions API tokens?

Type: research
Label: wayfinder:research
Status: resolved
Assignee: Tsvetan Ivanov (research subagent)
Map: [AFS Multi Pixel map](../map.md)

## Question

From Meta primary sources: can a third-party app use Facebook Login for Business / Business Login to list a merchant's pixels (datasets) and obtain a Conversions API access token per pixel (system user tokens, partner integrations)? Which permissions (`ads_management`, `business_management`, etc.) and what level of app review and business verification are required, and how long does it take? Token lifetime and revocation. If manual entry stays, how can a pasted pixel ID + CAPI token be validated via the Graph API? Is there a Meta partner program (for example CAPI Gateway or a partner integration) relevant to a Shopify app?

## Answer

Findings: branch `research/meta-connection-options`, file `research/meta-connection-options.md`.

- **Feasible:** Facebook Login for Business has a "Conversions API partner integration" template. One login gives a never-expiring system-user token for the merchant's business. We list pixels via `/<biz>/owned_pixels` and `/<biz>/client_pixels`, and one token sends to every granted pixel, so no per-pixel paste.
- **Permissions:** `ads_read` (covers sending server events) and `business_management`; production also lists `ads_management` and `pages_read_engagement`.
- **Gates:**
  - App Review for Advanced Access: "within a week".
  - Business Verification: up to ~14 business days (from a search snippet).
  - Tech Provider check: ~5 days.
  - A Marketing API access tier that needs 500 or 1,500 calls in 15 days (sources disagree).
  - Realistically several weeks overall.
- **Lifetime and revocation:** tokens never expire by default (60-day option). The merchant revokes in Business Settings → Connected apps, with no disconnect webhook, so we must detect failures. We can revoke with `oauth/revoke`.
- **Other paths:** none skips review. Meta Business Extension is allow-list only, CAPI Gateway runs in the advertiser's cloud, and the partner program is a badge.
- **Validating manual entry:** `GET /<pixel>?fields=id,name,owner_business,is_unavailable`. `test_event_code` isn't a dry run (events are kept), and `/debug_token` likely can't inspect Events Manager tokens.
- **Uncertain:** whether an Events Manager token can read its pixel; whether the login popup works inside the Shopify admin iframe; the tier threshold.
