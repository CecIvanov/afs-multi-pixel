// config.mjs — the single source of truth for app identity, for Node.
//
// Both the Shopify (React Router) service and any Node script import this so the
// app's name, handle, scopes, plan catalog and feature flags all come from the
// one file: app.config.json. Infra values (DB host, URLs, secrets) still come
// from the environment; identity comes from here.
//
//   import { appConfig, resolveDbName, resolveImagePrefix } from "../scripts/config.mjs";
//   appConfig.app.name              // "My Shopify App"
//   resolveDbName("dev")            // "myapp_dev"

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const configPath = process.env.APP_CONFIG_PATH || join(repoRoot, "app.config.json");

/** The parsed app.config.json. Frozen so nothing mutates the shared identity. */
export const appConfig = Object.freeze(
  JSON.parse(readFileSync(configPath, "utf8")),
);

const slug = appConfig.app?.slug || "myapp";
const ids = appConfig.identifiers || {};

/** Human-facing application name (UI titles, emails, legal). */
export const appName = appConfig.app?.name || "My Shopify App";
/** Shopify app handle (managed-pricing URL, app-proxy subpath). */
export const appHandle = appConfig.app?.handle || "my-shopify-app";

/** Docker image / container / metrics prefix. Defaults to the slug. */
export function resolveImagePrefix() {
  return ids.imagePrefix || slug;
}

/** Per-environment database name: prod is bare, others are suffixed. */
export function resolveDbName(env = process.env.APP_ENV || "dev") {
  const prefix = ids.databaseNamePrefix || slug;
  return env === "prod" || env === "production" ? prefix : `${prefix}_${env}`;
}

/** The plan catalog (managed-pricing mirror), sorted by ascending rank. */
export function billingPlans() {
  return [...(appConfig.billing?.plans || [])].sort((a, b) => a.rank - b.rank);
}
