# Join the browser Purchase with orders/create and send the hashed Server Purchase

Type: AFK
Status: open
Assignee:
Blocked by: 07
Spec: §3.2 step 4, §6 (`PendingPurchase`, `Webhook`), §7
Backlog: [backlog.md](backlog.md)

## What

The worker's `orders/create` handler and the stored browser Purchase meet in `PendingPurchase` by order ID (either may arrive first). When both are there, send the Server Purchase with hashed email, phone, name and address. No browser Purchase (no consent), no Server Purchase. Hash or delete the raw `orders/create` payload once processed. Expire unmatched rows after 7 days.

## Acceptance criteria

- [ ] A consented purchase on the UAT store gives one deduplicated Purchase per Market Pixel with customer data parameters
- [ ] A purchase without marketing consent gives no Server Purchase
- [ ] No raw name, email, phone or address remains in the database after processing
- [ ] Automated tests: join in both arrival orders, no-consent case, hashing
