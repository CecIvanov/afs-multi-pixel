# Require the active subscription to the one paid plan

Type: AFK
Status: open
Assignee:
Blocked by: 01, 00
Spec: §1, §5 (billing)
Backlog: [backlog.md](backlog.md)

## What

**Re-scoped (2026-10-01):** the template has managed billing (plan catalog in `app.config.json`, reconcile, an enforcement kill-switch). **Remaining:**
- Make the catalog one paid plan with the exact handle from ticket 00, `trialDays: 0`, and no free plan (check the engine accepts that).
- Agree on the no-subscription behaviour.

The original text below is kept for reference.


Read the shop's active app subscription and compare it with the exact plan handle (from the Partner Dashboard ticket, via env). Show the plan badge. Decide and implement what happens without an active subscription (the spec leaves this open; propose: the admin shows a 'Choose plan' screen linking to Shopify's plan page, and the Relay endpoint stops accepting events for that shop).

## Acceptance criteria

- [ ] The plan handle comes from config, no amounts anywhere in code
- [ ] A shop with the active plan sees the Markets page and the plan badge
- [ ] Behaviour without an active subscription agreed with the user and implemented
