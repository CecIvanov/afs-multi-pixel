import { defineConfig, devices } from "@playwright/test";

// Embedded Shopify admin E2E. NOTE: spread devices['Desktop Chrome'] into every
// project — a HeadlessChrome user-agent makes App Bridge fail the session-token
// exchange (surfaces as a phantom "410 Gone"). Capture the admin session once in
// global-setup into storageState.json (login is captcha-gated) and reuse it.
export default defineConfig({
  testDir: "./tests",
  retries: 2,
  workers: 1,
  timeout: 60_000,
  use: {
    ...devices["Desktop Chrome"],
    baseURL: process.env.E2E_APP_URL,
    video: "off",
    trace: "on-first-retry",
  },
  projects: [
    { name: "smoke", use: { ...devices["Desktop Chrome"] } },
  ],
});
