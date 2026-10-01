# e2e-ui — Playwright smoke test

A starting point for real-browser E2E against the embedded Shopify admin.

```bash
cd e2e-ui
npm install
npx playwright install chromium
E2E_APP_URL=https://your-tunnel-or-app.example npx playwright test
```

Without `E2E_APP_URL` the smoke test skips. To test the app **inside the admin
iframe** (not just the landing page), add a `global-setup.ts` that logs into a
development store once and saves `storageState.json`, then reuse it (admin login
is captcha-gated and blocks automation). Keep the `Desktop Chrome` device on every
project — a HeadlessChrome UA breaks App Bridge's session-token exchange.
