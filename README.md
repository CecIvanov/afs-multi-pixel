# Shopify App Template

A production-grade starting point for building embedded Shopify apps. It distills
the proven architecture of a live multi-carrier logistics app (Dostavi.bg) down to
the domain-agnostic spine every Shopify app needs — **embedded admin UI, Shopify
managed billing, multi-tenant PostgreSQL, asynchronous webhook processing, and
self-healing offline-token refresh** — so a new app starts from a compliant,
tested foundation instead of a blank page.

> **Status.** This repository is being scaffolded phase by phase. Present today:
> the single configuration source, the database setup scripts, a **runnable stack**
> (FastAPI + Celery + a durable job worker + Postgres + Redis), a **real embedded
> Shopify app** (OAuth, Polaris/App-Bridge shell, `afterAuth` → tenant upsert), and
> the **async webhook engine** — every webhook records + enqueues a durable DB-backed
> job (dedupe, priority, backoff, dead-letter, stale-reaper) processed out-of-band,
> with GDPR redaction wired through it, **Shopify managed billing** — a
> config-driven plan catalog, a Partner-API reconcile state machine (with the
> trial-downgrade fix), rank-based feature gates, metered usage, and the
> enforcement kill-switch — and **offline-token auto-refresh** so expiring
> App-Store tokens are renewed (proactively on a beat + reactively on a 401)
> before a background job can ever hit a dead token. It also ships the **test harness** (ephemeral Postgres,
> `make test`), **CI**, dual-source + parity **guard tests**, and the
> **`init-template` scaffolder** that turns it into a new app in one command. See
> [docs/SETUP.md](docs/SETUP.md) to run it and [SEAMS.md](SEAMS.md) for what you edit.

---

## Table of contents

- [Philosophy](#philosophy)
- [Architecture](#architecture)
- [One configuration place](#one-configuration-place)
- [Quick start](#quick-start)
- [Database setup](#database-setup)
- [Repository layout](#repository-layout)
- [Environments &amp; secrets](#environments--secrets)
- [The seams you actually touch](#the-seams-you-actually-touch)
- [Testing](#testing)
- [Built for Shopify](#built-for-shopify)
- [Roadmap](#roadmap)

---

## Philosophy

Every file inherited from the source app falls into one of three buckets. This
tag drives what the template ships and what a new app extends:

| Tag | Meaning |
| --- | --- |
| **Lift** | Reusable core — domain-agnostic spine, kept verbatim or lightly generalized (app-factory, webhook queue, billing engine, tenant model, request correlation, Docker entrypoint). |
| **Strip** | Domain-specific — deleted, or reduced to one labelled example so it is never mistaken for the framework. |
| **Seam** | Extension point — the finite, documented surface a new app edits (name, scopes, nav, plan catalog, webhook handlers, i18n). |

The goal: you change the **seams**, and inherit everything else working.

---

## Architecture

Two cooperating services share one PostgreSQL database but own disjoint tables.

```
Shopify Admin / Webhooks / Managed Billing
                 │
        ┌────────▼─────────┐        HTTPS + X-Internal-Key       ┌──────────────────────┐
        │   shopify/  (Node)│ ─────────────────────────────────▶ │   backend/  (Python)  │
        │  React Router v7  │                                    │  FastAPI + Celery      │
        │  · OAuth + session│                                    │  · canonical Tenant DB │
        │  · embedded admin │                                    │  · durable job queue   │
        │  · webhook receipt│ ◀───────────────────────────────── │  · workers + beat      │
        └────────┬──────────┘                                    └───────────┬───────────┘
                 │ Prisma: Session table only                                │ SQLAlchemy: everything else
                 └──────────────────────────┬─────────────────────────────────┘
                                    ┌────────▼────────┐        ┌─────────┐
                                    │   PostgreSQL     │        │  Redis  │
                                    └──────────────────┘        └─────────┘
```

- **`shopify/`** — React Router v7 on `@shopify/shopify-app-react-router`, App
  Bridge v4 + Polaris, Prisma for OAuth session storage. Owns OAuth, the embedded
  admin, and webhook receipt (HMAC verify, then ack fast).
- **`backend/`** — FastAPI + SQLAlchemy 2 + Alembic, Celery + Redis for async
  work, Prometheus metrics. Owns the canonical `tenants` record and all heavy
  processing (jobs, billing reconcile, compliance).
- **Trust boundary** — the Node BFF calls the Python `/internal/*` API with a
  shared secret (`X-Internal-Key`); the backend is never internet-exposed.

---

## One configuration place

**The application's name — and everything derived from it — is set in exactly one
file: [`app.config.json`](app.config.json).** No hardcoded app names scattered
across two languages; no fragile find-and-replace.

```jsonc
{
  "app": {
    "name": "AFS Multi Pixel",      // ← the name. Shown in UI, emails, legal.
    "handle": "afs-multi-pixel",    // Shopify app handle (managed-pricing URL, proxy)
    "slug": "afsmultipixel"                // short id → images, containers, network, DB, keys
  },
  "identifiers": { ... },          // derived from slug; override only on collisions
  "shopify":  { "apiVersion": "2026-10", "scopes": ["read_markets", "write_pixels", "read_customer_events", "read_orders"] },
  "billing":  { "mode": "managed", "plans": [ ... ] },
  "featureFlags": { ... }
}
```

### How the one file reaches everything

Three tiny loaders — one per runtime — read the same file, so identity never
diverges:

| Runtime | Loader | Used by |
| --- | --- | --- |
| Shell / Docker | [`scripts/lib/config.sh`](scripts/lib/config.sh) → `load_app_config` | DB scripts, start scripts, `docker-compose` env |
| Node | [`scripts/config.mjs`](scripts/config.mjs) → `appConfig`, `resolveDbName()` | the `shopify/` service |
| Python | [`backend/app/app_config.py`](backend/app/app_config.py) → `get_app_config()` | the `backend/` service + Celery |

Verify it yourself:

```bash
# shell
source scripts/lib/config.sh && load_app_config dev && echo "$APP_NAME / $DB_NAME"
# node
node -e 'import("./scripts/config.mjs").then(m=>console.log(m.appName, m.resolveDbName("dev")))'
# python
python3 -c 'import sys; sys.path.insert(0,"backend"); from app.app_config import get_app_config as c; print(c().name, c().database_name("dev"))'
```

All three print `AFS Multi Pixel / afsmultipixel_dev`.

### What lives where (and why)

`app.config.json` holds **identity** (name, handle, plans, scopes, flags) — the
things that define *which app this is*. It is safe to commit. Two other files
hold what must **not** live with identity:

- **`.env.<stack>`** — non-secret infra wiring (DB host/port, Redis URL). Committed.
- **`.credentials.<stack>`** — secrets (DB password, Shopify keys, internal key).
  Gitignored; only the `.example` twin is committed.

### Field reference

| Path | Purpose |
| --- | --- |
| `app.name` | Human-facing application name (UI titles, emails, legal copy). |
| `app.handle` | Shopify app handle — managed-pricing URL and app-proxy subpath. |
| `app.slug` | Short identifier; default source for every value in `identifiers`. |
| `app.primaryLocale` | Default admin UI locale. |
| `app.privacyPolicyUrl` / `app.termsUrl` | Surfaced in the app footer (App Store requirement). |
| `identifiers.imagePrefix` | Docker image / container / metrics prefix. |
| `identifiers.sharedNetwork` | External Docker network name (lets stacks co-exist on one host). |
| `identifiers.celeryKeyPrefix` | Redis/Celery key prefix — **must be unique per env** on a shared Redis. |
| `identifiers.databaseNamePrefix` / `databaseUserPrefix` | Base of the per-env DB name/user (`afsmultipixel_dev`, prod is bare `afsmultipixel`). |
| `identifiers.testDbSentinel` | The only DB name the destructive test/reset fixtures will touch. |
| `shopify.apiVersion` | Admin API version. Kept in sync with `shopify.app.toml` by a guard test. |
| `shopify.scopes` | Access scopes. Must match `SCOPES` in `.env` and the toml. |
| `billing.mode` | `managed` \| `api` \| `disabled`. |
| `billing.plans[]` | Plan catalog — the local mirror of your Partner-Dashboard plans. |
| `featureFlags` | Per-tenant flags, default off; ships with one example. |

---

## Quick start

```bash
# 1. Name your app — one command rewrites the identity + creates env files.
node scripts/init-template.mjs --name "My App"     # or: make init

# 2. Fill in the secrets it created for you.
$EDITOR .credentials.dev        # set DATABASE_PASSWORD, Shopify keys, INTERNAL_API_KEY

# 3. Bring the DEV stack up (Postgres, Redis, API, worker, beat, jobs, UI).
#    The API applies migrations on boot; Postgres/Redis run as containers.
./scripts/start.sh dev          # or: make dev  ·  uat: ./scripts/start.sh uat

#    Then:
#      UI      http://127.0.0.1:3000
#      API     http://127.0.0.1:8000/api/v1/health
#      Docs    http://127.0.0.1:8000/docs
#    Stop with ./scripts/stop.sh dev  (add --volumes to wipe the DB).

# Alternatively, provision only the database against an existing Postgres:
#   ./scripts/db/setup.sh dev
```

You also need a Shopify **Partner app per environment** (see [Environments](#environments)).
Full walk-through in [`docs/SETUP.md`](docs/SETUP.md).

---

## Environments

The template ships **three separate environments from day 0** — `dev`, `uat`, and
`production` — each a **separate Shopify app, database, and backend stack**. They can run
side-by-side on one host.

| Concern | dev | uat | production |
| --- | --- | --- | --- |
| Shopify app (toml) | `shopify.app.toml` | `shopify.app.uat.toml` | `shopify.app.production.toml` |
| App handle | `<handle>` | `<handle>-uat` | `<handle>-production` |
| Database | `<slug>_dev` | `<slug>_uat` | `<slug>` (bare) |
| Containers | `<slug>-*-dev` | `<slug>-*-uat` | `<slug>-*-production` |
| Ports (UI/API) | 3000 / 8000 | 3010 / 8010 | 3020 / 8020 |
| Billing | per `.env.dev` | **none**: custom app, `SHOPIFY_BILLING_MODE=disabled` | Shopify App Pricing: `shopify-test` < `light` (app.config.json) |
| Settings (non-secret) | `.env.dev` (local) | `.env.uat` (**committed**) | `.env.production` (**committed**) |
| Secrets | `.credentials.dev` (local) | `.credentials.uat` (VPS only) | `.credentials.production` (VPS only) |

`.env.uat` / `.env.production` hold only non-secret settings and live in git. The
`.credentials.<env>` files hold the secrets, are never committed, and are created and
edited directly on the VPS from `.credentials.example` (`chmod 600`). Then, **per
environment**:

```bash
# 1. Create a Partner app for the env; put its client id/secret in .credentials.<env> (on the VPS)
# 2. Link the env's toml:
cd shopify && npm run config:link:uat     # or config:link (dev) / config:link:production
# 3. Bring the env's stack up (separate db + backend):
./scripts/start.sh uat                    # dev · uat · production
# 4. Deploy the env's extensions/config:
npm run deploy:uat                        # deploy (dev) · deploy:uat · deploy:production
```

Separation is mechanical: every container name, image tag, volume, compose
project, and Celery/Redis key prefix is suffixed with the env, and the ports
differ — so `dev`, `uat`, and `production` never collide on one machine.

---

## Database setup

One database, two migration histories with **disjoint** table sets:

- **Prisma** owns the Shopify OAuth `Session` table (in `shopify/`).
- **Alembic / SQLAlchemy** owns every domain table — `tenants`, `billing_plans`,
  `webhook_events`, the async job queue, … (in `backend/`).

Keeping their tables disjoint is what lets both tools migrate the same database
without stepping on each other.

### Scripts

| Command | What it does |
| --- | --- |
| `./scripts/db/setup.sh [env]` | One-command bootstrap: create role + database + extensions, run migrations, seed plans. **Idempotent.** |
| `./scripts/db/migrate.sh [env]` | Alembic `upgrade head` (backend) + Prisma `migrate deploy` (Shopify). Skips a step whose service isn't scaffolded yet. |
| `./scripts/db/seed.sh [env]` | Upsert the `billing.plans` from `app.config.json` into `billing_plans`. |
| `./scripts/db/reset.sh [env]` | **Destructive** drop + recreate — non-prod only, triple-guarded. |

The role/database SQL is a parametrized template
([`scripts/db/setup-database.sql.template`](scripts/db/setup-database.sql.template))
rendered with proper identifier quoting by
[`scripts/lib/db.sh`](scripts/lib/db.sh); the DB **name and user come from
`app.config.json`**, the **password from `.credentials.<env>`**.

> **Guardrails.** `reset.sh` refuses production outright, requires the target name
> to carry the env suffix, and asks you to type the database name to confirm. The
> test suite's truncation fixtures will only ever touch `identifiers.testDbSentinel`.

### Runtime migrations

In containers, the backend applies `alembic upgrade head` on startup — gated so
**only one replica migrates** (the `api` service; all others set
`RUN_DB_MIGRATIONS=false`). Prisma is baselined on the shared DB rather than
blindly deployed. `setup.sh` is for first-time / local provisioning.

---

## Repository layout

```
ShopifyAppTemplate/
├─ app.config.json            # ← the single configuration place  [present]
├─ .env.example               # non-secret infra, per stack        [present]
├─ .credentials.example       # secrets, per stack (gitignored)    [present]
├─ scripts/
│  ├─ config.mjs              # Node identity loader               [present]
│  ├─ lib/
│  │  ├─ config.sh            # shell identity loader              [present]
│  │  └─ db.sh                # DB render/apply helpers            [present]
│  └─ db/
│     ├─ setup-database.sql.template · setup.sh · migrate.sh · seed.sh · reset.sh   [present]
├─ backend/                   # Python · FastAPI + Celery          [present]
│  ├─ app/
│  │  ├─ app_config.py        # Python identity loader
│  │  ├─ config.py · app_factory.py · main.py · logging_config.py
│  │  ├─ db/ · middleware/ · api/  (health + shared-key internal route)
│  │  ├─ models.py            # Base only; domain tables land in Phase 1
│  │  └─ workers/             # celery_app · tasks · metrics sidecar
│  ├─ alembic/ · alembic.ini · pytest.ini
│  └─ Dockerfile · docker-entrypoint.sh   # migrate-on-startup (api only)
├─ shopify/                   # Node UI — placeholder health server [present]
│  ├─ scripts/serve.mjs · package.json · Dockerfile               #  (RR app: Phase 1)
├─ packages/                  # shared libs                        [present]
│  ├─ logger/ (TS) · app_logger/ (Py)   # byte-identical JSON shape
│  └─ app_metrics/ (Py)                 # Prometheus, HTTP + worker
├─ docker-compose.yml (+ .dev / .prod)  # api · worker · beat · ui · pg · redis  [present]
├─ scripts/  start.sh · stop.sh · logs.sh [env] · init-template.mjs · lib/{compose,config,credentials}.sh  [present]
├─ docs/  SETUP.md · SEAMS.md                                      [next phase]
└─ README.md                  # this file                          [present]
```

---

## Environments &amp; secrets

Two-tier layering keeps non-secret config in git and secrets out:

- Committed `.env.<stack>` holds infra with `${VAR}` references.
- Gitignored `.credentials.<stack>` holds the real secrets, sourced (`set -a`)
  **before** compose so the `${VAR}` references resolve.

Multiple stacks (`dev` / `staging` / `prod`) co-exist on one host because every
container name, image tag, Docker network and Redis key is prefixed by the app
slug + env. **On a shared Redis, `celeryKeyPrefix` must be unique per env** or
environments consume each other's tasks.

---

## The seams you actually touch

A new app changes this finite surface and inherits the rest:

1. `app.config.json` — name, handle, scopes, plan catalog, feature flags.
2. The `afterAuth` backend-sync stub — first-run provisioning per app.
3. The webhook handler stubs — your domain topics.
4. The nav config array — drives the admin sidebar.
5. The i18n catalog — `en` + your locales (a parity test guards key drift).
6. `packages/integration_contract/` — your external-service DTOs.

Two values have **two sources of truth** and ship with a guard test: `SCOPES`
(`.env` ↔ `app.config.json` ↔ `shopify.app.toml`) and the API version
(`app.config.json` ↔ `shopify.app.toml`).

---

## Testing

A three-layer pyramid ships with the services (next phase):

- **Python** — `pytest` with `unit` / `integration` / `flow` / `e2e` markers;
  an ephemeral tmpfs Postgres, and a guard that refuses to run destructive
  fixtures unless the DB name matches `identifiers.testDbSentinel`.
- **Node** — the built-in `node --test` runner; logic is extracted into pure
  helpers and tested directly rather than mocking the Shopify SDK.
- **E2E** — Playwright smoke test asserting the embedded app renders in the App
  Bridge iframe.

TDD / reproduce-first is the working rule: write a failing test that asserts the
spec, never one that pins current (possibly buggy) output. A CI stub runs all
layers plus the parity + dual-source guard tests.

---

## Help &amp; support

A **Help page** (`/app/help`) ships with three sections — **Support**, **FAQ**,
and **How-to**. Edit the FAQ/How-to content in `shopify/app/help-content.ts`; set
support channels in `app.config.json`'s `support` block. A floating **"Chat on
Viber" button** appears on every admin screen — but only when you opt in
(`support.viber.enabled: true` + a number); it's **off by default**.

## Built for Shopify

The template ships compliant by default: embedded session-token auth, the three
mandatory GDPR compliance webhooks + `app/uninstalled` + `app/scopes_update`,
Shopify managed billing, contextual save bar (no dead-ends), accessibility lint,
a self-serve Help page, and a self-contained privacy/terms page. A new app adds
domain routes on top without re-earning the baseline.

---

## Roadmap

| Phase | Deliverable |
| --- | --- |
| **0a — identity + DB + docs** | Single config source, database setup scripts, this README. **done** |
| **0b — skeleton + bring-up** | Docker compose (ui/api/worker/beat/pg/redis), Dockerfiles + migrate-on-startup entrypoint, shared logger/metrics packages, FastAPI app-factory + health, Celery worker/beat, `start.sh <env>`. **done** |
| **1 — auth + tenant** | React Router embedded app (`shopify.server.ts`, Polaris/App-Bridge shell, `afterAuth` → tenant upsert), `Tenant` + `TenantMetadata` + plan tables, Alembic baseline, install/uninstall/session-sync internal API, GDPR + lifecycle webhooks, async shop-info capture. Backend verified against Postgres (9 pytest); UI typechecks + builds. **← you are here** |
| **2 — webhooks + async** | `WebhookEvent` (delivery dedup) + durable `AsyncJob` queue (SKIP-LOCKED claim, in-flight caps, backoff, dead-letter, stale-reaper), ingest service + operation→handler registry, `job_pool` worker, GDPR redaction. Verified against Postgres (20 pytest) + 6 Node tests. **← you are here** |
| **3 — billing** | Config-driven plan catalog + pure semantics (both languages), managed-pricing helpers, Partner-API reconcile state machine (trial-downgrade fix), rank-based feature gates, metered usage with atomic guard, enforcement kill-switch. Verified (30 pytest + 9 node). **← you are here** |
| **4 — tests + CI + scaffolding** | Ephemeral-Postgres harness (`run-tests-isolated.sh` + `make test`), Playwright smoke skeleton, the parity + dual-source guard tests, GitHub Actions CI, `init-template` scaffolder, `SEAMS.md`, `Makefile`. Verified: `run-tests.sh` green (32 pytest + 11 node); `init-template` renames cleanly. **done** |

**All four headline requirements are built, validated against a real Postgres, and committed** — tenant-on-install, async webhook processing, managed billing, and the uninstall/redact lifecycle. The template is ready to seed new apps.
