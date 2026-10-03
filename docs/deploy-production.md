# Deploying the Production stack on VPS Black

The Production App ("AFS Multi Pixel", client ID `4e22a50fb4b433f72347339801cf7e3f`, handle `afs-multi-pixel`) is the **public App Store app**, billed through Shopify App Pricing (managed pricing). It runs on **VPS Black**:
- **Containers:** `afsmultipixel-*-production`. The UI is on `127.0.0.1:3120` and the API on `127.0.0.1:8120`.
- **Database:** the VPS's own Postgres, database and role `afsmultipixel` (`DB_NAME` / `DB_USER` in `.env.production`).
- **Proxy:** Caddy-black, at `https://multi-pixel-prd.adfeedstudio.com`.

The steps are the same as **[UAT](deploy-uat.md)** with `production` in place of `uat`; this page lists only what differs, and the checks before resubmitting for review. Steps marked *(VPS)* run in the repo checkout on VPS Black, *(dev machine)* on your machine.

---

## 1. Secrets *(VPS)*

```bash
cp .credentials.example .credentials.production
chmod 600 .credentials.production
```

| Key | Value |
|---|---|
| `DATABASE_PASSWORD` | `openssl rand -hex 24` (hex only: it goes inside a database URL). |
| `INTERNAL_API_KEY` | `openssl rand -hex 32`. |
| `SHOPIFY_API_SECRET` | Partner Dashboard → AFS Multi Pixel → Client credentials → **Client secret**. |
| `TOKEN_ENC_KEY` | `openssl rand -hex 32`. **Back it up and never change it**: losing it makes every stored Conversions API token unreadable. |
| `SHOPIFY_PARTNER_ACCESS_TOKEN` | Partner Dashboard → Settings → Partner API clients, with access to the app's billing. Reads each shop's plan. |

**Nothing else goes in this file.** `SHOPIFY_API_KEY`, `SHOPIFY_APP_GID`, `SHOPIFY_PARTNER_ORG_ID`, `DB_NAME`, `DB_USER` and every other setting live in `.env.production`. The file is loaded into the shell, which wins over `.env.production`, so a leftover line — even an empty one — would override the real value (an empty `SHOPIFY_APP_GID` turned the plan check off for every shop). The start script refuses to start when the file sets a key `.env.production` has, or when any secret above is empty.

## 2. Database, Postgres access, start *(VPS)*

```bash
./scripts/db/setup.sh production --provision-only
./scripts/db/allow-docker-access.sh production
./scripts/start-production.sh
```

`start-production.sh` builds and starts the stack, then runs **`scripts/smoke.sh production`**: every container healthy, the API health check, and over the public URL `/` (200), `/privacy` and `/terms` (200, with their text) and an unsigned `POST /webhooks/…` (401 — not 404 or 500). It exits non-zero if any check fails; fix that before going further.

## 3. Caddy *(VPS)*

Paste the **PRODUCTION block** from `deploy/caddy/Caddyfile.snippet` into Caddy-black's Caddyfile and reload (see UAT step 6). Then run `./scripts/smoke.sh production` again: the public checks need Caddy.

## 4. Release the app config and extensions *(dev machine)*

```bash
cd shopify
npm ci
npm run config:link:production   # once per machine
npm run deploy:production        # shopify app deploy --config shopify.app.production.toml
```

This sends Shopify the URL, scopes, every webhook subscription (including `app_subscriptions/update` and the three GDPR topics), the theme app embed and the Web Pixel. Run it again after any change to `shopify.app.production.toml` or `shopify/extensions/`. Protected customer data (name, email, phone, address) must be approved for the public app before `orders/create` deploys.

## 5. Partner Dashboard checks (billing)

Shopify's plan page (`admin.shopify.com/store/<store>/charges/afs-multi-pixel/pricing_plans`) is Shopify's, not ours; it 404s when it has no plan to show. Before resubmitting:
- **Distribution → Pricing:** Shopify App Pricing (managed pricing) is on.
- **`light`:** public, active, display name and every price field filled (a yearly price too if yearly is on).
- **`shopify-test`:** private (or removed), so reviewers don't see it.
- The plan handles are exactly `light` and `shopify-test` (`app.config.json` billing.plans).
- The app's admin URL is `/apps/afs-multi-pixel/…` (the handle in `SHOPIFY_APP_HANDLE`).

## 6. End-to-end check before resubmitting

On a **fresh development store** (another org's if you can — your own org's stores can see private plans):
1. Install from the listing. You land on Shopify's plan page, not in the app.
2. Choose `light` and approve the test charge. You land back in the app, on Markets, with the plan stored (`./scripts/logs-production.sh ui`: `billing.reconciled` with `hintConfirmed: true`).
3. Click **Plan** in the app nav: Shopify's plan page opens (no 401).
4. Click the app's name in the admin sidebar: the app opens (not the landing page).
5. Uninstall, then check the Partner Dashboard → Logs: `app/uninstalled` and `shop/redact` answered 200.
6. Reinstall: you're sent to Shopify's plan page again (the plan was reset on uninstall).

Record steps 1–4 as the proof for the review.

## Day to day *(VPS)*

| Task | Command |
|---|---|
| Update the code | `git pull && ./scripts/start-production.sh` (rebuilds, restarts, migrates, smoke-checks) |
| Smoke check only | `./scripts/smoke.sh production` |
| Logs | `./scripts/logs-production.sh [api\|jobs\|worker\|beat\|ui\|redis]` |
| Backup | `./scripts/db/backup.sh production` |
| Look at the data | `sudo -u postgres psql afsmultipixel` |
