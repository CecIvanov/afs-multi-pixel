# Can the Official Meta App run alongside us without double counting, and can we detect it?

Type: research
Label: wayfinder:research
Status: resolved
Assignee: Tsvetan Ivanov (research subagent)
Map: [AFS Multi Pixel map](../map.md)

## Question

From Meta and Shopify primary sources: in the Facebook & Instagram sales channel, can the merchant set data sharing to off (or limit it) while keeping catalog sync and shops working? What exactly does each data-sharing level send (browser pixel, CAPI)? Can our app detect that the channel is installed or which pixel it uses (Admin API, web pixel list, metafields)? What does Meta do when two sources send the same event with different event IDs to the same pixel?

## Answer

Findings: branch `research/official-meta-app-coexistence`, file `research/official-meta-app-coexistence.md`.

- **Data sharing can be switched off** in the Facebook & Instagram channel ("Enable data-sharing"; a pixel can only be attached while it's on). Catalog sync follows product publishing to the channel, not data sharing, so keeping the catalog and Shops with sharing off looks supported. No source states it outright, so it needs a test-store check.
- **Levels:** Standard sends browser pixel events only, without customer personal data. Enhanced and Maximum add the Conversions API ("sends the purchase event") plus name, location, email and phone. Whether Maximum sends funnel events server-side too is unclear.
- **Detection:** we can't see which pixel the channel uses (`webPixel`/`serverPixel` return only our own; storefront pixels are sandboxed). `appByHandle("facebook").installation` might reveal whether the channel is installed, if a third-party token can read it (unverified).
- **Same pixel ≈ double counting.** Meta deduplicates only a browser event against a server event on the same pixel (event name + event ID, or fbp/external_id, within 48 h). Two browser events or two server events are never deduplicated. Different pixels count each conversion once per dataset.
- **Setup to recommend:** channel data sharing off, or a Market Pixel that is never the channel's pixel.
