# Send AddToCart and checkout events from the strict Web Pixel

Type: AFK
Status: open
Assignee:
Blocked by: 04
Spec: §3.1
Backlog: [backlog.md](backlog.md)

## What

Strict Web Pixel: AddToCart (Market from `_mpx_market`), InitiateCheckout, AddPaymentInfo and Purchase (`checkout_completed`, Market from `checkout.localization.market.id`), sent with `fetch` to Meta `/tr` with `_fbp`/`_fbc` reuse or creation and facebook.com cookies, in the Official Meta App's event shape (`content_ids` product IDs, `content_type: product_group`, AddToCart value = unit price, Purchase `eid` = `purchase-<orderId>`). Consent-gated. Each event also sends its encrypted Relay.

## Acceptance criteria

- [ ] Each checkout event reaches the pixel of the checkout's Market
- [ ] Purchase uses event ID `purchase-<orderId>`
- [ ] No event without marketing consent
- [ ] Unit tests for payload building (`content_ids`, value, currency)
