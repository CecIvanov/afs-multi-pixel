# UAT release checklist

Run on the **UAT App** before every **Production App** release (spec §9). Copy this file's checklist into the release's GitHub issue or PR, tick each line, and write down anything that failed.

**Setup:**
- The UAT App is deployed, with config and both extensions from `npm run deploy:uat`.
- The test store has at least two Markets on different domains. Each has its own Market Pixel and Conversions API token, with a test event code set.
- Meta Pixel Helper is installed. Events Manager → Test events is open for each pixel.

## 1. Install and setup

- [ ] Install from the custom-distribution link. The Markets page lists every Market of the store as a tile.
- [ ] The setup strip shows **App embed** off. "Turn on the app embed" opens the theme editor with the embed selected. After saving, a reload shows it on.
- [ ] Add a pixel to each Market:
  - Save stays disabled until Check with Meta passes.
  - Check with Meta shows the pixel name and owner.
  - A wrong token or pixel ID fails the check with Meta's message.
- [ ] Read the `market_pixels` row in Postgres. `capi_token_encrypted` is ciphertext, not the token.
- [ ] Settings → Customer events lists the app's Web Pixel. Its settings carry the mapping, endpoint and public key.

## 2. Full Standard Funnel, per Market

For each Market, browse its domain with marketing consent given:

- [ ] Each of these events reaches **only that Market's pixel**, as both Browser and Server, deduplicated in Events Manager:
  - PageView
  - ViewContent (product, collection, cart)
  - Search
  - AddToCart
  - InitiateCheckout
  - AddPaymentInfo
  - Purchase
- [ ] Purchase carries event ID `purchase-<orderId>`. The Server Purchase shows customer information parameters (email, phone, name, address) as matched.
- [ ] `content_ids` are product IDs with `content_type: product_group`. AddToCart's value is the unit price.
- [ ] The Market's tile shows the counts and the chart. The event log lists the events with Meta's answer.

## 3. Consent off

- [ ] With marketing (or sale of data) declined in the store's cookie banner, there's no `fbevents.js` and no request to facebook.com or `/api/events`, on the storefront and at checkout.
- [ ] A purchase without consent creates no Server Purchase. The event log shows nothing for it.

## 4. Token rejection, pause and resume

- [ ] Replace one Market's token in Meta (revoke it) and browse that Market:
  - The tile turns **Token problem** with Meta's message.
  - Server Events show as `paused` in the event log.
  - Browser Events still reach the pixel.
- [ ] Paste a new token. The paused events (under 7 days old) are sent, and the tile turns **Sending**.
- [ ] Block Meta (for example, a bad network on the VPS for a few minutes). Events retry on the 1 min / 5 min / … backoff and are sent once it's back. Nothing is lost.

## 5. Markets lifecycle

- [ ] Add a Market in Shopify. Within a minute, or on reload, it shows as **New · no pixel**, with when it was added.
- [ ] Delete a mapped Market. Its tile and its mapping disappear. The metafield and the Web Pixel settings no longer list it.
- [ ] Add a custom domain to a Market. It reaches the Relay allowlist (`tenants.storefront_hosts`) on app open, or within a day.

## 6. Relay security

- [ ] A Relay replayed from another Origin is rejected and logged.
- [ ] A Relay for a Market → pixel pair that isn't in the mapping is rejected and logged.

## 7. Plan (Production App only; UAT runs with billing disabled)

- [ ] Without the plan, the admin shows only the Plan page, and Relays are rejected.
- [ ] After choosing the plan, the Markets page loads with the plan badge.

## 8. Restart and uninstall

- [ ] Redeploy or restart the stack. The storefront keeps working with no merchant action, because the key and endpoint are republished on start.
- [ ] Uninstall:
  - The Conversions API tokens are gone from `market_pixels`.
  - New Relays for the shop are rejected.
  - `shop/redact` (48 h later) deletes everything for the shop.

## 9. Operations

- [ ] Last night's backup exists locally and at `BACKUP_REMOTE`. It restores into an empty database with `scripts/db/restore.sh`.
- [ ] The beat log shows `retention.daily.completed` and `worker.storefront_hosts_dispatch.completed` in the last 24 h.

## Open checks from spec §11

Run these once on the UAT App, and again whenever Shopify changes the area. Record the result and the date here.

| Check | Result | Date |
|---|---|---|
| Whether B2B buyers get the same Market on the storefront and at checkout | | |
| Whether `markets/update` fires on condition or status changes | | |
| Whether uninstalling removes the Web Pixel and the app-owned metafield automatically | | |
| Whether an Events Manager token can read its own pixel (Check with Meta). If not, fall back to a test event | | |
| Liquid `localization.market` is still available (ADR 0001); check the changelog | | |
