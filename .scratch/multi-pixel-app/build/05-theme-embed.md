# Send storefront events from the theme app embed, gated by consent

Type: AFK
Status: open
Assignee:
Blocked by: 04
Spec: §2, §3.1, §4 (setup strip)
Backlog: [backlog.md](backlog.md)

## What

Theme app embed: read `localization.market.id`, write the `_mpx_market` cookie, load `fbevents.js` only when `marketingAllowed()` and `saleOfDataAllowed()` are true, and send PageView, ViewContent (product, cart, collection) and Search with `fbq('trackSingle', <Market Pixel>, …)` in the Official Meta App's event shape. Send each event's Relay (encrypted) to the backend. Show the embed status in the setup strip via `app.extensions()`, with the activation deep link.

## Acceptance criteria

- [ ] With marketing consent, each Market's storefront events reach only that Market's pixel (Meta Pixel Helper / Events Manager)
- [ ] Without consent, `fbevents.js` isn't loaded and nothing is sent
- [ ] A Market with no pixel sends nothing
- [ ] The setup strip shows the embed off/on and the deep link turns it on
