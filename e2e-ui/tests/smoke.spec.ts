import { test, expect } from "@playwright/test";

// Phase-0 smoke: the app's landing page renders. Set E2E_APP_URL to your running
// app (e.g. the Shopify CLI tunnel or a deployed URL) to run it; skipped otherwise.
//
// The real embedded-admin check (app renders inside the App Bridge iframe) needs a
// captured admin session — see playwright.config.ts and add a global-setup that
// logs in once into storageState.json. This file is the starting point.

const APP_URL = process.env.E2E_APP_URL;

test.skip(!APP_URL, "set E2E_APP_URL to run the smoke test");

test("landing page responds", async ({ page }) => {
  const response = await page.goto("/");
  expect(response?.status()).toBeLessThan(500);
  await expect(page.locator("body")).toBeVisible();
});
