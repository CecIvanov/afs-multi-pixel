# How does an app follow a store's Markets over time and detect that its theme app embed is on?

Type: research
Label: wayfinder:research
Status: resolved
Assignee: Tsvetan Ivanov (research subagent)
Map: [AFS Multi Pixel map](../map.md)

## Question

From shopify.dev: which webhooks (`markets/*` or others) report Markets being created, updated, deleted or merged at Admin API `2026-10`; how to list Markets (including B2B and region types) and their stable IDs; how Market IDs behave across Liquid, Admin API and checkout. How can an app detect that its theme app embed is enabled on the published theme (reading `settings_data.json` via the Asset/Theme API, deep links to activate it), and what happens with themes or theme switches where it's off? Reuse `research/market-detection-in-web-pixel`.

## Answer

Findings: branch `research/markets-lifecycle-and-embed`, file `research/markets-lifecycle-and-embed.md`.

- **Webhooks:** 2026-10 has `markets/create`, `markets/update` and `markets/delete` (scope `read_markets`), plus `markets_backup_region/update`. Payloads carry only a numeric `id` (create and update add `name`, `type`, `status`), so treat each one as a signal to re-fetch Markets.
- **No merge webhook.** The parent/child Market hierarchy (new in 2026-10: `parentMarkets`/`childMarkets`) has no webhook either.
- **Listing:** the `markets` query filters by `type` (REGION, COMPANY_LOCATION, LOCATION, CHANNEL, NONE); `status` is ACTIVE or DRAFT. `Market.id` is a GID with no `legacyResourceId`, and the merchant can change `handle`. Liquid and webhooks use numeric IDs, while the Admin API and checkout use GIDs. Normalise to the numeric tail, as the POC does.
- **⚠ Risk to an inherited decision:** Shopify lists Liquid `localization.market` among the deprecated single-market endpoints, because "Market IDs are no longer stable identifiers": adding a child Market changes the ID returned. The migration guide is paused, with no replacement and no removal date. Graduated into [What happens to storefront Market detection when Liquid `localization.market` is deprecated or Market IDs shift?](15-market-id-stability.md).
- **Embed detection:** in the embedded admin, `app.extensions()` reports embed status on the published theme with no extra scope. From the backend, read `config/settings_data.json` of the `MAIN` theme via GraphQL `files` (needs `read_themes`, which the app doesn't request yet) and find our block with `disabled` not true. The REST Asset API is legacy for new public apps.
- **Activation deep link:** `/admin/themes/current/editor?context=apps&template=…&activateAppId={api_key}/{handle}`. Embeds are off by default after install.
- **Theme switches:** `themes/publish` fires, but toggling the embed fires nothing, so detection must poll. A newly published theme may have the embed off. Checkout routing still works without the embed.
- **Needs a test store:** whether `markets/update` fires on condition or status changes; whether B2B buyers get the same Market in Liquid and checkout; what the embed's `available`/`unavailable` states mean; whether a duplicated theme keeps the embed setting.
