# Start the production app on a clean branch with Postgres, Docker and two app configs

Type: AFK
Status: open
Assignee:
Spec: §5, §8, §9
Needs: the UAT App from 00 (step 1) for the last criterion only
Backlog: [backlog.md](backlog.md)

## What

A fresh Shopify React Router app (Node/TypeScript, Prisma) on a new clean branch, with no POC code copied. Postgres instead of SQLite. One Docker image run as two processes, **web** and **worker** (the worker loop can be an empty poller for now). Two app configs (`shopify.app.uat.toml`, `shopify.app.production.toml`) and `.env` examples. The encryption-at-rest helper (AES-256-GCM, modelled on AFS `packages/meta-connector/src/crypto.ts`, own key from env). Test runner set up.

## Acceptance criteria

- [ ] New branch with no shared history with the POC code (only the spec, map and ADRs may be carried)
- [ ] `docker compose up` starts web + worker + Postgres locally; Prisma migrations run on start
- [ ] Both app configs exist; secrets only in env, `.env*` gitignored with `.example` files committed
- [ ] Encryption helper with unit tests (round trip, wrong key fails)
- [ ] The embedded admin opens on the UAT App with an empty Markets page
