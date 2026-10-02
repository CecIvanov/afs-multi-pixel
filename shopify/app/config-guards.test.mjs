// Dual-source-of-truth guards. Identity that lives in more than one file must
// agree, or a partial edit silently ships a mismatch. These run in `node --test`
// (and CI).

import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const appDir = dirname(fileURLToPath(import.meta.url));
const shopifyDir = join(appDir, "..");
const repoRoot = join(shopifyDir, "..");

const appConfig = JSON.parse(readFileSync(join(repoRoot, "app.config.json"), "utf8"));
const shopifyServer = readFileSync(join(appDir, "shopify.server.ts"), "utf8");

// dev/uat/production are SEPARATE Shopify apps; each toml is standalone, so scopes +
// api_version must be kept identical across all of them (and app.config.json).
const ENV_TOMLS = ["shopify.app.toml", "shopify.app.uat.toml", "shopify.app.production.toml"];

function tomlValue(toml, key) {
  const m = toml.match(new RegExp(`^\\s*${key}\\s*=\\s*"([^"]*)"`, "m"));
  return m ? m[1] : null;
}

// The @shopify ApiVersion enum member for a given YYYY-MM API version.
const API_VERSION_ENUM = {
  "2025-10": "October25",
  "2025-07": "July25",
  "2026-01": "January26",
  "2026-04": "April26",
  "2026-07": "July26",
  "2026-10": "October26",
};

test("API version agrees across app.config.json, every env toml, and shopify.server.ts", () => {
  const configVersion = appConfig.shopify?.apiVersion;
  const enumMember = API_VERSION_ENUM[configVersion];
  assert.ok(enumMember, `no ApiVersion enum mapping for ${configVersion} — add it to this test`);
  assert.ok(
    shopifyServer.includes(`ApiVersion.${enumMember}`),
    `shopify.server.ts should use ApiVersion.${enumMember} for API version ${configVersion}`,
  );
  for (const file of ENV_TOMLS) {
    const toml = readFileSync(join(shopifyDir, file), "utf8");
    assert.equal(tomlValue(toml, "api_version"), configVersion, `${file} api_version != app.config.json apiVersion`);
  }
});

test("scopes agree between app.config.json and every env toml", () => {
  const configScopes = (appConfig.shopify?.scopes || []).join(",");
  for (const file of ENV_TOMLS) {
    const toml = readFileSync(join(shopifyDir, file), "utf8");
    assert.equal(tomlValue(toml, "scopes"), configScopes, `${file} scopes != app.config.json shopify.scopes`);
  }
});

// Copies outside the tomls that hard-code the same values: fallbacks used when
// app.config.json can't be read, the SCOPES the Node app actually requests at
// runtime, and the setup docs. Each must follow app.config.json.
function readRepoFile(path) {
  return readFileSync(join(repoRoot, path), "utf8");
}

function capture(text, regex, file) {
  const m = text.match(regex);
  assert.ok(m, `${file}: expected to find ${regex}`);
  return m[1];
}

test("API version fallbacks and docs agree with app.config.json", () => {
  const configVersion = appConfig.shopify?.apiVersion;
  const copies = [
    ["backend/app/services/shopify_shop_info_service.py", /\.get\("apiVersion", "([^"]+)"\)/],
    ["scripts/lib/config.sh", /_config_get shopify\.apiVersion ([0-9-]+)\)/],
    ["docs/SETUP.md", /\(currently `([0-9-]+)`\)/],
    ["README.md", /"apiVersion": "([0-9-]+)"/],
  ];
  for (const [file, regex] of copies) {
    assert.equal(capture(readRepoFile(file), regex, file), configVersion, `${file} API version != app.config.json apiVersion`);
  }
});

test("runtime SCOPES in env examples and the compose default agree with app.config.json", () => {
  const configScopes = (appConfig.shopify?.scopes || []).join(",");
  const copies = [
    [".env.example", /^SCOPES=(.*)$/m],
    [".env.uat", /^SCOPES=(.*)$/m],
    [".env.production", /^SCOPES=(.*)$/m],
    ["docker-compose.yml", /SCOPES: \$\{SCOPES:-([^}]*)\}/],
  ];
  for (const [file, regex] of copies) {
    assert.equal(capture(readRepoFile(file), regex, file), configScopes, `${file} SCOPES != app.config.json shopify.scopes`);
  }
});

// Webhook subscriptions: each toml is standalone, so the three must declare the
// same topics at the same URIs, and every URI needs its webhooks.*.tsx route.
function webhookSubscriptions(toml) {
  const subs = [];
  for (const block of toml.split("[[webhooks.subscriptions]]").slice(1)) {
    const kind = block.match(/^\s*(topics|compliance_topics)\s*=\s*\[([^\]]*)\]/m);
    const uri = block.match(/^\s*uri\s*=\s*"([^"]*)"/m);
    if (!kind || !uri) continue;
    const topics = [...kind[2].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
    subs.push(`${kind[1]}=${topics.join(",")} -> ${uri[1]}`);
  }
  return subs.sort();
}

test("webhook subscriptions agree across every env toml and each URI has a route", () => {
  const [devFile, ...otherFiles] = ENV_TOMLS;
  const expected = webhookSubscriptions(readFileSync(join(shopifyDir, devFile), "utf8"));
  for (const file of otherFiles) {
    assert.deepEqual(webhookSubscriptions(readFileSync(join(shopifyDir, file), "utf8")), expected, `${file} webhooks != ${devFile}`);
  }
  for (const sub of expected) {
    const uri = sub.split(" -> ")[1];
    const route = `webhooks.${uri.replace(/^\/webhooks\//, "").replaceAll("/", ".")}.tsx`;
    assert.ok(existsSync(join(appDir, "routes", route)), `${uri} has no route file app/routes/${route}`);
  }
});

test("the v1 webhook topics are all subscribed", () => {
  const subs = webhookSubscriptions(readFileSync(join(shopifyDir, ENV_TOMLS[0]), "utf8")).join("\n");
  for (const topic of [
    "app/uninstalled",
    "app/scopes_update",
    "orders/create",
    "markets/create",
    "markets/update",
    "markets/delete",
    "customers/data_request",
    "customers/redact",
    "shop/redact",
  ]) {
    assert.match(subs, new RegExp(`[=,]${topic}[, ]`), `${topic} is not subscribed`);
  }
});

// .env.uat and .env.production are committed, so they must never carry a secret:
// every key the .credentials.<stack> files hold is forbidden in them.
test("committed .env.uat / .env.production define no secret from .credentials.example", () => {
  const keys = (text) => [...text.matchAll(/^([A-Z][A-Z0-9_]*)=/gm)].map((m) => m[1]);
  const secretKeys = new Set(keys(readRepoFile(".credentials.example")));
  assert.ok(secretKeys.has("TOKEN_ENC_KEY") && secretKeys.has("SHOPIFY_API_SECRET"));
  for (const file of [".env.uat", ".env.production"]) {
    const leaked = keys(readRepoFile(file)).filter((key) => secretKeys.has(key));
    assert.deepEqual(leaked, [], `${file} defines secrets; move them to .credentials.<stack> on the VPS`);
  }
});

// The client ID lives in two places per deployed stack: the app's toml (Shopify
// CLI) and .env.<stack> (the running app). They must name the same app.
test("SHOPIFY_API_KEY in .env.uat / .env.production matches the toml client_id", () => {
  for (const [env, toml] of [
    [".env.uat", "shopify/shopify.app.uat.toml"],
    [".env.production", "shopify/shopify.app.production.toml"],
  ]) {
    const apiKey = capture(readRepoFile(env), /^SHOPIFY_API_KEY=(.*)$/m, env);
    const clientId = capture(readRepoFile(toml), /^client_id = "(.*)"$/m, toml);
    assert.ok(clientId, `${toml} has no client_id`);
    assert.equal(apiKey, clientId, `${env} SHOPIFY_API_KEY != ${toml} client_id`);
  }
});
