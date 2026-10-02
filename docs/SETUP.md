# Setup

From zero to a running embedded app on a development store.

## 1. Name the app (one place)

Edit [`app.config.json`](../app.config.json): set `app.name`, `app.handle`, `app.slug`.
Everything else (DB name, image tags, Celery keys) derives from `slug`.

## 2. Create the Shopify Partner app

1. In the [Partner Dashboard](https://partners.shopify.com) → **Apps → Create app → Create app manually**.
2. Copy the **Client ID** and **Client secret**.
3. You'll set the App URL + redirect URLs after you have a public tunnel (step 5).

## 3. Configure environment

```bash
cp .env.example .env.dev
cp .credentials.example .credentials.dev
```

In `.credentials.dev` set:
- `DATABASE_PASSWORD` — any value for local dev
- `INTERNAL_API_KEY` — any non-default secret
- `SHOPIFY_API_KEY` / `SHOPIFY_API_SECRET` — the Client ID / secret from step 2.
  Used by the Node BFF **and** the backend (the backend renews expiring offline
  tokens with a `grant_type=refresh_token` exchange — see SEAMS §3a), so both the
  `ui` and the `api`/`worker`/`beat`/`jobs` containers read them.

In `.env.dev` confirm `SCOPES` matches `shopify.app.toml`'s `[access_scopes]`
(they must agree — a Phase 4 guard test enforces this), and set `SHOPIFY_APP_URL`
once you have a tunnel.

## 4. Link the Partner app to the toml

```bash
cd shopify
npm install
npm run config:link      # choose your app; writes client_id into shopify.app.<env>.toml
```

Keep `api_version` in `shopify.app.toml` equal to `shopify.apiVersion` in
`app.config.json` (currently `2026-10`).

## 5. Run it

**Option A — Shopify CLI (recommended for dev; provides the tunnel):**
```bash
cd shopify
npm run dev              # opens a tunnel, sets URLs, installs on a dev store
```

**Option B — the full Docker stack (UI + API + worker + beat + jobs + Postgres + Redis):**
```bash
./scripts/start.sh dev          # dev · uat · production are separate stacks
```
The API applies migrations on boot and seeds the plan catalog. The UI serves the
embedded app; point your Partner app's App URL at it (behind a tunnel/HTTPS).

## 7. Repeat for UAT and production

`dev`, `uat`, and `production` are **separate Shopify apps + databases + backends**
(see the Environments table in the README). For each: create its Partner app, set
its non-secret values in the committed `.env.<env>`, create `.credentials.<env>` on
the VPS from `.credentials.example` (never committed), `npm run config:link:<env>`,
then `./scripts/start.sh <env>` and `npm run deploy:<env>`. The UAT App is a custom app with no billing (`SHOPIFY_BILLING_MODE=disabled`):
every shop counts as subscribed and the admin has no Plan page.

## 7a. Deploy UAT / production on the VPS

UAT and production use the **VPS's own Postgres** (no Postgres container); each
stack runs its own Redis container. The containers reach Postgres at
`host.docker.internal:5432` (`DATABASE_HOST` / `DATABASE_PORT` in `.env.<stack>`),
which docker-compose maps to the host's Docker bridge. On the VPS, once per stack:

```bash
cp .credentials.example .credentials.uat && chmod 600 .credentials.uat   # fill the secrets
./scripts/db/setup.sh uat --provision-only     # role + database in the host Postgres (sudo)
./scripts/db/allow-docker-access.sh uat        # pg_hba line for the containers; checks listen_addresses
./scripts/start.sh uat                         # api migrates and seeds plans on start
```

Same with `production` (database and role `afsmultipixel`; UAT's are
`afsmultipixel_uat`). If `allow-docker-access.sh` reports that Postgres doesn't
listen on the Docker bridge, set `listen_addresses = 'localhost,172.17.0.1'` in
`postgresql.conf` and restart Postgres; keep 5432 closed in the firewall.
Both stacks run on VPS Black, whose Caddy (`~/Projects/Caddy-black`, host
networking) proxies each public URL to `127.0.0.1:<UI_PORT>`: 3110 UAT, 3120
production (Blacklist COD owns 3010/3020 there). Paste
`deploy/caddy/Caddyfile.snippet` into Caddy-black's Caddyfile and reload it.
Nightly backups: `scripts/db/backup.sh <stack>` (cron line in the script).

## 6. Verify the install round-trip

Install the app on a development store. On the backend:

```bash
psql "$DATABASE_URL" -c "SELECT shop_domain, status FROM tenants;"
psql "$DATABASE_URL" -c "SELECT m_key, m_value FROM tenants_metadata;"
```

You should see the tenant row (status `active`) and, shortly after, the captured
store profile (`store_name`, `store_contact_email`, …) written asynchronously.

## Two-source-of-truth footguns (guard tests land in Phase 4)

- `SCOPES` (`.env`) ↔ `[access_scopes]` (`shopify.app.toml`)
- API version: `shopify.apiVersion` (`app.config.json`) ↔ `api_version` (`shopify.app.toml`) ↔ `ApiVersion.*` (`shopify.server.ts`)
