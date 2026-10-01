# Where does production run, and how are its data and secrets stored?

Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: Tsvetan Ivanov
Blocked by: 01, 08
Map: [AFS Multi Pixel map](../map.md)

## Question

Database (Postgres vs other; shared with AFS or not), hosting (single VPS vs multi-instance, behind `adfeedstudio-lb`?), backups, migrations, CAPI token and relay key storage (encryption at rest, key management), and relay key rotation.

## Answer

**A Docker application on a VPS with Postgres (the user's call, 2026-10-01).** SQLite from the POC is replaced by Postgres (the app's own database; per [What in the AdFeed Studio stack could AFS Multi Pixel reuse?](08-afs-stack-reuse.md), it can live on an existing Postgres server with its own role), with Prisma migrations. Conversions API tokens are encrypted at rest ([Which customer data does v1 request, and how does it meet App Store and GDPR obligations?](13-compliance-plan.md)). Single instance in v1. Backups and relay key rotation fold into the deployment and security details still in the map's fog.
