# What happens to storefront Market detection when Liquid `localization.market` is deprecated or Market IDs shift?

Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: Tsvetan Ivanov
Map: [AFS Multi Pixel map](../map.md)

## Question

The Markets research ([How does an app follow a store's Markets over time and detect that its theme app embed is on?](06-markets-lifecycle-and-embed.md)) found that Shopify lists Liquid `localization.market` among the deprecated single-market endpoints. Its reason is that Market IDs are no longer stable: adding a child Market changes the ID returned. There's no replacement and no removal date yet.

The POC's storefront Market detection (theme embed → `_mpx_market` cookie) and the Pixel Mapping keyed by numeric Market ID both rest on this. For v1, do we:
- ship on `localization.market` and watch the changelog,
- key the Pixel Mapping by something sturdier (handle, or resolve the parent/child hierarchy so a child Market inherits its parent's pixel), or
- add a fallback signal (country + language → Market resolved server-side)?

Also decide how the mapping survives a Market whose ID changes (no webhook covers hierarchy changes), and whether a short targeted research or a test-store task is needed first (for example, adding a child Market on `gpay3y-2v` and watching which IDs Liquid and checkout report).

## Answer

**Ship on `localization.market`, surface unmapped Markets, no inheritance (agreed with the user, 2026-10-01).**
- v1 keeps the POC's storefront detection (Liquid `localization.market.id` → `_mpx_market` cookie) and the Pixel Mapping keyed by numeric Market ID. The deprecation is recorded as a known dependency; watch Shopify's paused migration guidance and changelog.
- "Most specific Market" is the behaviour we want, since we route by the Market the shopper is actually in. The real gap is a new or nested Market appearing with no Market Pixel.
- On `markets/create` (and on each Markets re-fetch), a Market with no Market Pixel is flagged as **unmapped** in the admin so the merchant can assign a pixel + token. The UI belongs in [How does the merchant set up and maintain their Pixel Mapping in the admin?](14-onboarding-and-mapping-ux.md).
- **No parent → child pixel inheritance in v1**: the "no fallback" rule stands.
