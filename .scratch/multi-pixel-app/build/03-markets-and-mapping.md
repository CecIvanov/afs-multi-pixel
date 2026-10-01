# Sync Markets and let the merchant map pixel + token pairs on the Market health page

Type: AFK
Status: open
Assignee:
Blocked by: 01, 02
Spec: §2, §4, §5, §6 (`Shop`, `Market`, `MarketPixel`)
Backlog: [backlog.md](backlog.md)

## What

Fetch the shop's Markets (`read_markets`) on install and app open, and on `markets/create|update|delete` (through the webhook inbox). New Markets without a pixel are flagged. The Market health home page (variant C, prototype on branch `prototype/admin-ux`): tiles for mapped and unmapped Markets, B2B/Draft labels, the plan badge placeholder, an empty summary row. The pixel editor modal: pixel ID (15–16 digits) + token both required, optional test event code, **Check with Meta** (`GET /<pixel>?fields=id,name,owner_business,is_unavailable`) must pass before Save, Remove pixel. Tokens stored encrypted.

## Acceptance criteria

- [ ] Markets on the UAT store appear as tiles; adding a Market in Shopify shows it as new and unmapped
- [ ] A deleted Market disappears with its mapping
- [ ] Save is impossible without both a valid pixel ID and a token that passed Check with Meta
- [ ] Tokens are encrypted in the database (verified by reading the row)
- [ ] The layout matches variant C at desktop and phone width
