#!/usr/bin/env bash
#
# setup.sh — one-command database bootstrap for an environment.
#
#   ./scripts/db/setup.sh [dev|test|staging|prod]     (default: dev)
#
# 1. Creates/updates the app role + database + extensions (as postgres superuser)
# 2. Runs migrations   (Alembic for the backend, Prisma for the Shopify session)
# 3. Seeds the billing plan catalog from app.config.json
#
# Idempotent — safe to re-run. Identity (db name, user) comes from app.config.json;
# the password comes from .credentials.<env> (auto-created with a dev default if
# missing).

set -euo pipefail
ENV_NAME="${1:-dev}"
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../lib/db.sh
source "${ROOT_DIR}/scripts/lib/db.sh"

require_command python3
require_command psql

db_connection_env "${ENV_NAME}"

echo "==> [${ENV_NAME}] Provisioning role '${DB_USER}' and database '${DB_NAME}'"
TMP_SQL="$(mktemp)"
trap 'rm -f "${TMP_SQL}"' EXIT
render_setup_sql "${TMP_SQL}"
run_psql_superuser "${TMP_SQL}"

echo "==> [${ENV_NAME}] Applying migrations"
APP_ENV="${ENV_NAME}" DATABASE_URL="${DATABASE_URL}" "${ROOT_DIR}/scripts/db/migrate.sh" "${ENV_NAME}"

echo "==> [${ENV_NAME}] Seeding billing plans"
APP_ENV="${ENV_NAME}" DATABASE_URL="${DATABASE_URL}" "${ROOT_DIR}/scripts/db/seed.sh" "${ENV_NAME}"

echo "==> [${ENV_NAME}] Database ready: ${DATABASE_URL/${DB_PASSWORD}/****}"
