#!/usr/bin/env node
/**
 * init-template.mjs — turn this template into YOUR app.
 *
 *   node scripts/init-template.mjs --name "Acme Ship" [--handle acme-ship] [--slug acmeship] [--yes]
 *
 * app.config.json is the single source of truth: the app name/handle/slug and the
 * infra identifiers derived from the slug (docker image prefix, shared network,
 * Celery key prefix, database name/user, the test-DB sentinel). This script edits
 * that file structurally, updates shopify.app.toml (read by the Shopify CLI, not
 * from the config), and does a scoped find/replace of the old identity across a
 * documented allow-list of files. Everything else derives at runtime.
 *
 * Idempotent: it replaces the CURRENT identity (whatever app.config.json says) with
 * the new one, so re-running with the same values is a no-op.
 */

import { readFileSync, writeFileSync, existsSync, copyFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createInterface } from "node:readline/promises";
import { stdin, stdout } from "node:process";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");

// Files where the placeholder identity literals appear (the fallback defaults +
// docs). app.config.json and shopify.app.toml are handled structurally above.
const REWRITE_FILES = [
  "docker-compose.yml",
  "docker-compose.dev.yml",
  "docker-compose.uat.yml",
  "docker-compose.prd.yml",
  "docker-compose.test.yml",
  "backend/app/config.py",
  ".env.example",
  ".env.uat.example",
  ".env.prd.example",
  ".env.test.example",
  "README.md",
];

// The per-env Shopify apps (each a separate app with its own handle).
const ENV_TOMLS = [
  { file: "shopify/shopify.app.toml", nameSuffix: "", handleSuffix: "" },       // base / dev
  { file: "shopify/shopify.app.uat.toml", nameSuffix: " (UAT)", handleSuffix: "-uat" },
  { file: "shopify/shopify.app.prd.toml", nameSuffix: "", handleSuffix: "-prd" },
];

function slugify(name) {
  return String(name).toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--yes" || a === "-y") args.yes = true;
    else if (a.startsWith("--")) args[a.slice(2)] = argv[++i];
  }
  return args;
}

function replaceAll(text, from, to) {
  return from && from !== to ? text.split(from).join(to) : text;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const configPath = join(ROOT, "app.config.json");
  const config = JSON.parse(readFileSync(configPath, "utf8"));

  const oldName = config.app.name;
  const oldHandle = config.app.handle;
  const oldSlug = config.app.slug;

  let name = args.name;
  if (!name && !args.yes) {
    const rl = createInterface({ input: stdin, output: stdout });
    name = (await rl.question(`App name [${oldName}]: `)).trim() || oldName;
    rl.close();
  }
  name = name || oldName;
  const handle = args.handle || slugify(name);
  const slug = args.slug || handle.replace(/-/g, "");

  // 1) app.config.json — identity + slug-derived identifiers.
  config.app.name = name;
  config.app.handle = handle;
  config.app.slug = slug;
  config.identifiers = {
    ...config.identifiers,
    imagePrefix: slug,
    sharedNetwork: `${slug}-shared`,
    celeryKeyPrefix: slug,
    databaseNamePrefix: slug,
    databaseUserPrefix: slug,
    testDbSentinel: `${slug}_test`,
  };
  writeFileSync(configPath, JSON.stringify(config, null, 2) + "\n");

  // 2) Per-env Shopify app tomls — each a SEPARATE app (own name + handle).
  for (const { file, nameSuffix, handleSuffix } of ENV_TOMLS) {
    const p = join(ROOT, file);
    if (!existsSync(p)) continue;
    let toml = readFileSync(p, "utf8");
    toml = toml.replace(/^(\s*name\s*=\s*)"[^"]*"/m, `$1"${name}${nameSuffix}"`);
    toml = toml.replace(/^(\s*handle\s*=\s*)"[^"]*"/m, `$1"${handle}${handleSuffix}"`);
    writeFileSync(p, toml);
  }

  // 3) Scoped find/replace of the old identity (longest-first) in the allow-list.
  const pairs = [
    [oldName, name],
    [oldHandle, handle],
    [oldSlug, slug],
  ].sort((a, b) => b[0].length - a[0].length);
  for (const rel of REWRITE_FILES) {
    const p = join(ROOT, rel);
    if (!existsSync(p)) continue;
    let text = readFileSync(p, "utf8");
    for (const [from, to] of pairs) text = replaceAll(text, from, to);
    writeFileSync(p, text);
  }

  // 4) Create per-env files from the examples (never overwrite) — dev/uat/prd
  //    are separate environments from day 0.
  const envFiles = [
    [".env.example", ".env.dev"],
    [".env.uat.example", ".env.uat"],
    [".env.prd.example", ".env.prd"],
    [".credentials.example", ".credentials.dev"],
    [".credentials.example", ".credentials.uat"],
    [".credentials.example", ".credentials.prd"],
  ];
  for (const [example, target] of envFiles) {
    const src = join(ROOT, example);
    const dst = join(ROOT, target);
    if (existsSync(src) && !existsSync(dst)) copyFileSync(src, dst);
  }

  console.log(`\n✅ Initialized "${name}" (slug: ${slug}).`);
  console.log(`   Shopify apps: ${handle} (dev) · ${handle}-uat · ${handle}-prd — three separate apps.\n`);
  console.log("Next steps (repeat per environment — dev, uat, prd):");
  console.log("  1. Create a Shopify Partner app for each env; put its client id/secret in .credentials.<env>");
  console.log("  2. cd shopify && npm install && npm run config:link[:uat|:prd]");
  console.log("  3. ./scripts/start.sh dev     (or uat / prd — separate stacks)");
  console.log("  4. See docs/SETUP.md for the full walk-through.\n");
}

main().catch((error) => {
  console.error("init-template failed:", error);
  process.exit(1);
});
