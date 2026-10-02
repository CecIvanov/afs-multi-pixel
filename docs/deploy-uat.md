# Deploying the UAT stack on VPS Black

The UAT App ("AFS Multi Pixel (UAT)", client ID `cbf79027737c8bcbd7657e9af8328383`) is a **custom app**: it has custom distribution and no billing. It runs on **VPS Black**:
- **Containers:** `afsmultipixel-*-uat`. The UI is on `127.0.0.1:3110` and the API on `127.0.0.1:8110`.
- **Database:** the VPS's own Postgres, with database and role `afsmultipixel_uat`.
- **Proxy:** Caddy-black, at `https://multi-pixel-uat.adfeedstudio.com`.

Do the steps in order. Steps marked *(VPS)* run in the repo checkout on VPS Black. Steps marked *(dev machine)* run on your machine.

---

## 0. One-time prerequisites

- *(dev machine)* Push the code, because the VPS clones it from GitHub:
  ```bash
  git push -u origin production
  ```
- **DNS:** add an A record `multi-pixel-uat.adfeedstudio.com` pointing at VPS Black's public IP.
- *(VPS)* Check the tools:
  - `docker compose version`
  - `python3 --version`: the scripts read `app.config.json` with it.
  - `sudo -u postgres psql -c 'select version()'`: Postgres is installed and reachable.
- **Firewall:** 80 and 443 are open (Caddy). 5432 stays closed to the internet.

## 1. Get the code onto the VPS *(VPS)*

```bash
git clone git@github.com:CecIvanov/afs-multi-pixel.git ~/Projects/afs-multi-pixel
cd ~/Projects/afs-multi-pixel
git checkout production
```

`.env.uat` (the non-secret settings) comes with the checkout. Check that it has the right values:
- `SHOPIFY_APP_URL=https://multi-pixel-uat.adfeedstudio.com`
- `SHOPIFY_API_KEY=cbf79027…`
- `UI_PORT=3110`
- `DATABASE_HOST=host.docker.internal`

## 2. Create the secrets file *(VPS)*

```bash
cp .credentials.example .credentials.uat
chmod 600 .credentials.uat
```

Fill these in `.credentials.uat`:

| Key | Value |
|---|---|
| `DATABASE_PASSWORD` | `openssl rand -hex 24`. Hex only: the password goes inside a database URL, so it must contain no `@`, `:` or `/`. Step 3 creates the role with it. |
| `INTERNAL_API_KEY` | `openssl rand -hex 32`. Guards the UI → API calls inside the stack. |
| `SHOPIFY_API_SECRET` | Partner Dashboard → AFS Multi Pixel (UAT) → Client credentials → **Client secret** |
| `TOKEN_ENC_KEY` | `openssl rand -hex 32`. Encrypts the Conversions API tokens and the Relay key. **Back it up somewhere safe and never change it**: losing it makes every stored token unreadable. |
| `SHOPIFY_PARTNER_ACCESS_TOKEN` | Leave empty. UAT has no billing. |

Don't add `SHOPIFY_API_KEY` here. It lives in `.env.uat`, and the scripts refuse to start if `.credentials.uat` sets it.

## 3. Create the database and its role in the VPS's Postgres *(VPS)*

```bash
./scripts/db/setup.sh uat --provision-only
```

- **What it does:** as the `postgres` superuser (via `sudo`), it creates or updates role `afsmultipixel_uat` with `DATABASE_PASSWORD` and database `afsmultipixel_uat`. It also adds the `pgcrypto` and `citext` extensions and grants the role full rights on the `public` schema.
- **Safe to re-run:** it's idempotent.
- **Default passwords:** it refuses to run while `DATABASE_PASSWORD` is empty or a dev default.
- **No tables yet:** the containers create them on start (step 5).

## 4. Let the containers reach Postgres *(VPS)*

```bash
./scripts/db/allow-docker-access.sh uat
```

The containers connect to `host.docker.internal:5432`, which is the VPS seen from inside Docker. Their connections come from Docker's addresses (`172.16.0.0/12`). The script:
- adds `host afsmultipixel_uat afsmultipixel_uat 172.16.0.0/12 scram-sha-256` to `pg_hba.conf` and reloads Postgres;
- checks that Postgres listens on the Docker bridge (`listen_addresses`).

If it says Postgres doesn't listen on the bridge:
1. Set `listen_addresses = 'localhost,172.17.0.1'` in `postgresql.conf`. Get the file's path with `sudo -u postgres psql -tAc 'SHOW config_file'`.
2. Run `sudo systemctl restart postgresql`.
3. Run the script again.

## 5. Start the stack *(VPS)*

```bash
./scripts/start-uat.sh
```

- **Builds and starts** redis, api, jobs, worker, beat and ui.
- **On start:**
  - The **api** applies the database migrations, writes the plan list and queues a republish of the storefront settings for installed shops.
  - The **ui** creates the Shopify session table.
  - The **jobs** container runs the webhook inbox and the Conversions API sender.

Check:
```bash
curl -s 127.0.0.1:8110/api/v1/health      # {"status":"ok",...,"env":"uat"}
curl -sI 127.0.0.1:3110 | head -1         # HTTP/1.1 200 (or a redirect)
./scripts/logs-uat.sh api                 # "Database migrations applied.", "billing.plan_catalog_synced"
```

If the api is unhealthy, run `./scripts/logs-uat.sh api`:
- "connection refused" or "no pg_hba.conf entry": go back to step 4.
- "password authentication failed": `.credentials.uat` and the role disagree. Re-run step 3.

## 6. Put it behind Caddy *(VPS)*

Paste the **UAT block** from `deploy/caddy/Caddyfile.snippet` into `~/Caddy-black/Caddyfile`. Commit it in that repo if you keep one. Then:

```bash
docker exec caddy-black caddy reload --config /etc/caddy/Caddyfile
curl -sI https://multi-pixel-uat.adfeedstudio.com | head -1
```

The first HTTPS request gets the certificate, so DNS (step 0) has to resolve first.

## 7. Release the app config and extensions to Shopify *(dev machine)*

1. Partner Dashboard → AFS Multi Pixel (UAT) → **API access → Protected customer data**: request access to **name, email, phone and address**.
   - **Why:** this lets the app match purchases to shoppers in Meta. The data is hashed and only used for the server Purchase.
   - **Do it first:** without it, Shopify refuses the `orders/create` webhook when you deploy. For a custom app the request is self-serve.
2. Deploy:
   ```bash
   cd shopify
   npm install
   npm run deploy:uat        # shopify app deploy --config shopify.app.uat.toml
   ```
   This sends Shopify the app URL, scopes, webhooks, the theme app embed and the Web Pixel. The Shopify CLI may ask you to log in the first time.

## 8. Install on the test store

1. Partner Dashboard → AFS Multi Pixel (UAT) → **Distribution** (custom distribution) → generate an **install link** for the test store (`gpay3y-2v.myshopify.com`), then open it and install.
2. **Uninstall the old POC app ("AFS Multi Pixel" test app) from that store first, if it's still installed.** Its embed and Web Pixel would send the same events to the same pixels, so every event would count twice.

## 9. Set it up in the store

Open the app in the store's admin. Home is the **Markets** page.

1. **Tiles:** each of the store's Markets should appear as a tile.
2. **Setup strip → "Turn on the app embed":** in the theme editor, switch on **AFS Multi Pixel** under App embeds and **Save**.
3. **Each Market you test → "Configure":**
   1. Paste the pixel ID and the Conversions API token.
   2. Choose **Check with Meta**, then **Activate pixel**.
   3. On the Market page, choose **Edit pixel and token**, add a test event code (from Events Manager → Test events), **Check with Meta** and **Save**.
4. **Consent banner:** make sure the store asks for cookie consent (Settings → Customer privacy). Tick the step in the setup strip.
5. **Test:** browse each Market's domain, allow cookies, then view a product, add it to the cart and check out.
   - Events Manager → Test events: each event should arrive once, as both Browser and Server.
   - The Market page's **Events** table shows them as **Sent**.

Then work through the full **[release checklist](release-checklist.md)**.

## Day to day *(VPS)*

| Task | Command |
|---|---|
| Update the code | `git pull && ./scripts/start-uat.sh` (rebuilds and restarts; migrations run on start) |
| Logs | `./scripts/logs-uat.sh [api\|jobs\|worker\|beat\|ui\|redis]` |
| Stop | `./scripts/stop-uat.sh`. Add `--volumes` to also drop Redis data. The database in the VPS's Postgres is never touched. |
| Backup | `./scripts/db/backup.sh uat` (the cron line is at the top of the script; set `BACKUP_REMOTE` for an off-VPS copy) |
| Look at the data | `sudo -u postgres psql afsmultipixel_uat` |

If you change `shopify.app.uat.toml` or anything under `shopify/extensions/`, run `npm run deploy:uat` again *(dev machine)*.
