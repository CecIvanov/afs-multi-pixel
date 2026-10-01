# Seams — the surface you edit

Building a new app on this template means changing a **finite, documented set of
seams** and inheriting everything else working. This is that complete surface.

Start with `node scripts/init-template.mjs --name "My App"` (or `make init`) — it
sets the identity seam (#1) for you. The rest you edit as you build features.

## 1. Identity — `app.config.json`

The single source of truth. `app.name` / `app.handle` / `app.slug`, and the
`identifiers` derived from the slug (docker image prefix, shared network, Celery
key prefix, database name/user, the test-DB sentinel). Read at runtime by the
shell (`scripts/lib/config.sh`), Node (`scripts/config.mjs`), and Python
(`backend/app/app_config.py`). Also holds `shopify.scopes`, `shopify.apiVersion`,
`billing.plans`, and `featureFlags`.

## 2. Scopes & API version — kept in sync across every env toml

There are three separate Shopify-app tomls (`shopify.app.toml` = dev,
`shopify.app.uat.toml`, `shopify.app.prd.toml`); each is standalone, so scopes +
webhooks must be **identical across all three** and match `app.config.json`.

- **Scopes**: `app.config.json` `shopify.scopes` **and** the `[access_scopes]` of
  every env toml. A guard test (`shopify/app/config-guards.test.mjs`) fails on drift.
- **API version**: `app.config.json` `shopify.apiVersion`, every toml's
  `api_version`, and `shopify/app/shopify.server.ts` (`ApiVersion.*`). Same guard.
- **Other copies** the same guard file checks: the API-version fallbacks in
  `backend/app/services/shopify_shop_info_service.py` and `scripts/lib/config.sh`,
  the version in `docs/SETUP.md` and `README.md`, and the runtime `SCOPES` in every
  `.env*.example` and the `docker-compose.yml` default.

## 2a. Environments — dev / uat / prd (separate apps)

Each env is a separate Shopify app + database + backend. Per-env identity lives in
`shopify.app.<env>.toml` (client_id/handle/URL) + `.env.<env>` (ports, handle, URL)
+ `.credentials.<env>` (secrets). `init-template` scaffolds all of it; the shared
identity (name/slug/plans) stays in `app.config.json`.

## 3. Backend behavior — `afterAuth` / post-install

- `shopify/app/tenant.server.ts` `ensureBackendTenant` runs on OAuth + every
  admin navigation. The backend `TenantService.create_tenant` enqueues a
  pluggable post-install job (`SHOP_INFO_FETCH`) — add your own first-run
  provisioning there.

## 3a. Offline token auto-refresh (do not remove)

Public App-Store apps use **expiring** Shopify offline tokens (Node enables this
via `future: { expiringOfflineAccessTokens }` in `shopify.server.ts`). If nothing
renews the token, every background Admin-API call 401s once it lapses — the app
silently dies for that store. This is wired end-to-end and works with **zero**
per-app changes; you only interact with it if you add Admin-API background jobs:

- **Storage**: `Tenant.refresh_token` / `access_token_expires_at` /
  `refresh_token_expires_at` / `shopify_refresh_token_revoked_at` (all from
  migration 001; sweep indexes from 005). Node pushes the token + expiries to the
  backend on every navigation (`/shopify/install`, `/shopify/session-sync`).
- **Proactive**: a 1-minute Celery beat (`dispatch_shopify_token_refresh`) →
  `ShopifyTokenRefreshService.discover_and_enqueue_refreshes` enqueues a durable
  `TOKEN_REFRESH` job for any tenant nearing expiry; the handler does the
  `grant_type=refresh_token` exchange and mirrors the rotated token back into the
  Prisma `Session` row (rotating refresh tokens are single-use).
- **Reactive**: `AsyncJobService._dispatch_with_auth_recovery` force-refreshes +
  retries once when any job's Admin-API call 401s.
- **Requires**: `SHOPIFY_API_KEY` / `SHOPIFY_API_SECRET` on the **backend**
  services (added to the `x-backend-env` anchor) — the exchange runs backend-side.
- **Cadence**: `shopify_token_refresh_lead_minutes` (5) /
  `shopify_refresh_token_renew_lead_days` (7) in `config.py`. A dead refresh chain
  sets `shopify_refresh_token_revoked_at` (merchant must re-auth).

## 4. Webhooks — topics + handlers

- Declare topics in all three env tomls (a guard test fails on drift or a missing
  route); add a `webhooks.<topic>.tsx` route whose action is `webhookAction`
  (`shopify/app/webhooks.server.ts`) — it verifies the HMAC, stores the webhook
  and answers 200. Routes do no other work.
- Map the topic to an operation in `backend/app/services/webhook_ingest_service.py`
  (`TOPIC_TO_OPERATION`) and register a handler with `@job_handler(...)` in
  `backend/app/services/job_processors.py`.

## 5. Async jobs — operations + handlers

Add an `AsyncJobOperation` (models.py), a `@job_handler`, and (if it's periodic)
a Celery beat entry in `backend/app/workers/celery_app.py`.

## 6. Billing — plan catalog + features + entitlements

- Plans: `app.config.json` `billing.plans` (handle, rank, `shopifyPlanName`,
  `monthlyQuota`, `features`). Mirror them in the Partner Dashboard.
- Features: list a feature on the plans that grant it; gate code with
  `BillingService.ensure_feature(...)`. Metered work: `ensure_within_quota(...)`.
- Mode: `SHOPIFY_BILLING_MODE` = `managed` | `api` | `disabled`.

## 7. GDPR — `CUSTOMER_PII_LOCATIONS`

In `backend/app/services/compliance_service.py`, `CUSTOMER_PII_LOCATIONS` lists
where customer-linked rows live, by order ID (for `customers/redact`), and
`SHOP_TABLES` is the FK-safe delete order for `shop/redact`. Add every new
tenant-scoped table to `SHOP_TABLES`.

## 8. UI — nav + pages

- Nav: the `<NavMenu>` list in `shopify/app/routes/app.tsx`.
- Pages: add `app.<name>.tsx` routes (Polaris web components, `s-page` / `s-section`).

## 8a. Help & support

- **Help content**: `shopify/app/help-content.ts` — the FAQ + How-to items rendered
  on the `/app/help` page. Edit these for your app.
- **Support channels + Viber FAB**: `app.config.json` `support` block — `email`
  and `viber.{enabled, numberE164, display, label}`. The floating "Chat on Viber"
  button (`components/viber-fab.tsx`) shows on every admin screen **only when
  `support.viber.enabled` is true and a number is set** — off by default.

## 9. Domain data — models + migrations

Add SQLAlchemy models in `backend/app/models.py` and an Alembic migration in
`backend/alembic/versions/`. Keep every tenant-scoped table carrying a
`tenant_id` FK.

## 10. External integrations — `packages/integration_contract/`

Your app's outbound-service DTOs live here (empty in the template). Add a
throttle-aware client under `backend/app/services/` for any Shopify-Admin or
third-party API you call.

---

**Guardrails that keep the seams honest** (run in CI): the two dual-source guards
(#2), the logger-shape parity and billing-semantics parity
(`backend/tests/test_guards.py`), and the full pytest + `node --test` suite.
