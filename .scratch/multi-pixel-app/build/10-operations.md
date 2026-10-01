# Add daily jobs, backups and the UAT release checklist

Type: AFK
Status: open
Assignee:
Blocked by: 07, 08
Spec: §8, §9, §11
Backlog: [backlog.md](backlog.md)

## What

Daily jobs: delete `Event` and `Webhook` rows older than 30 days and expired `PendingPurchase` rows, re-fetch storefront domains. Nightly Postgres dump kept 14 days, stored off the VPS. Write the UAT release checklist (spec §9 plus the open checks in §11) as a file in the repo.

## Acceptance criteria

- [ ] Cleanup jobs run daily and are logged
- [ ] A backup restores successfully into an empty database
- [ ] Release checklist committed; the §11 checks have been run once and their results recorded
