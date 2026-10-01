# How does the merchant set up and maintain their Pixel Mapping in the admin?

Type: prototype
Label: wayfinder:prototype
Status: resolved
Assignee: Tsvetan Ivanov
Blocked by: 06, 10, 11
Map: [AFS Multi Pixel map](../map.md)

## Question

Prototype the embedded admin: the onboarding checklist (connect Meta, switch on the theme embed, consent banner present, Official Meta App setting), how Markets are listed and Market Pixels assigned, and what the merchant sees when Markets are added, renamed or removed after mapping.

Settled inputs: pixel ID + Conversions API token is a mandatory pair per mapped Market (validate on save, show Meta errors); new Markets show as **unmapped**; the embed status comes from `app.extensions()` with the activation deep link; the Official Meta App gets no warning; English only; the active plan is read by handle. Also include a health view for the merchant (what's sending, what's failing) beyond the raw Event log.


## Answer

**Variant C, "Market health", is the app UI (the user's call, 2026-10-01).** Prototype: branch `prototype/admin-ux`, file `.scratch/multi-pixel-app/prototype/admin-ux-prototype.html` (all three variants; published privately at https://claude.ai/artifact/XGPKyEw8Yqdmk6eg4NmRcK, open variant C with `#C`).

What variant C fixes for the spec:
- **Home = the Markets page.** A summary row (Markets sending, Markets needing attention, browser events in 24 h, share that reached Meta via server), then **one tile per Market**:
  - Mapped tile: name and regions, status badge, pixel name and ID, the error text if any, a 24-hour events-per-hour chart, Browser / Server / Purchase counts, last event, "Edit pixel" (or "Update token" when Meta rejects it), and "View events".
  - Unmapped tile (dashed): "No events are sent for shoppers in this Market", with "Add pixel". New Markets say when they were added and get a primary button. B2B and Draft Markets are labelled.
- **Setup** is a compact strip at the top (App embed, Pixels, Consent, Verified in Meta) shown until everything is done. There's no separate wizard.
- **Pixel editor (modal):** pixel ID (15–16 digits) and Conversions API token, both required; an optional test event code; "Check with Meta" must pass before Save; "Remove pixel".
- **Event log** opens in a side drawer: all events from the page header, or one Market's from its tile. Columns: time, event, Market, sent as (Browser / Server / Relay), status (sent, skipped, waiting, rejected, error), Meta's answer.
- The plan badge is shown in the page header.
