# What in the AdFeed Studio stack could AFS Multi Pixel reuse?

Type: research
Label: wayfinder:research
Status: resolved
Assignee: Tsvetan Ivanov (research subagent)
Map: [AFS Multi Pixel map](../map.md)

## Question

Read the local AFS repos (`~/Projects/adfeedstudio-saas`, `adfeedstudio-saas-portal`, `adfeedstudio-lb`): how accounts, orgs and auth work; how billing is done (Stripe, plans, quotas); the database (Postgres?) and migrations; hosting and deployment (VPS, Docker, load balancer, Caddy), secrets handling and encryption at rest; any existing Shopify or Meta integration. Summarise what could be shared with a Shopify app (database, hosting, accounts, Meta app) and what the coupling would cost.

## Answer

Findings: branch `research/afs-stack-reuse`, file `research/afs-stack-reuse.md` (paths below are relative to `~/Projects`).

- **Hosting: reuse.** VPS-Black's single Caddy edge (`Caddy-black/Caddyfile`) already routes one site block per app to a loopback port, including the AFS Shopify app and the SaaS sites. `adfeedstudio-lb/Caddyfile.saas` is a template if we go multi-instance.
- **Database: reuse the Postgres server, not the SaaS database.** Give Prisma its own role and database (the `adfeedstudio-saas/scripts/setup-postgres.sh` pattern). The SaaS schema deliberately excludes Shopify concepts.
- **Encryption at rest: copy** the ~50-line AES-256-GCM helper (`adfeedstudio-saas/packages/meta-connector/src/crypto.ts`), with our own key. The POC stores `capiToken` in plaintext.
- **Billing: don't reuse.** The SaaS bills through Stripe, and App Store requirement 1.2.1 forbids off-platform billing. Follow `ads_images_generator/packages/billing/` (Shopify Billing API).
- **Accounts: don't reuse.** The SaaS uses Google login and its own orgs; the app authenticates by shop. A store ↔ AFS org link, if wanted, would copy ADR 0023 (link code; designed, not built).
- **Meta app: keep separate.** The AFS Meta app has a pending `catalog_management` review that extra scopes would put at risk. Its review playbook is reusable.
- **Website: reuse.** An entry in `adfeedstudio-website/src/data/apps.ts` gives the privacy and listing pages.
- **Cost of sharing:** VPS-Black, Caddy and Postgres become a single point of failure for every AFS app, and the checkout relay would compete with image rendering for capacity.
- **Uncertain:** Postgres capacity and version for the event log; which server runs the POC; whether future Meta features need `ads_management`.
