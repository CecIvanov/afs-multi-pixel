#!/usr/bin/env bash
#
# setup.sh — one-command database bootstrap for an environment.
#
#   ./scripts/db/setup.sh [dev|uat|production] [--provision-only]   (default: dev)
#
# 1. Creates/updates the app role + database + extensions (as postgres superuser)
# 2. Runs migrations   (Alembic for the backend, Prisma for the Shopify session)
# 3. Seeds the billing plan catalog from app.config.json
#
# On the VPS use --provision-only (step 1 only): the containers do steps 2 and 3
# themselves on start (the api runs Alembic and syncs the plan catalog, the ui runs
# the Prisma bootstrap), so the VPS needs no Python or Node.
#
# Idempotent — safe to re-run. Identity (db name, user) comes from app.config.json;
# the password comes from .credentials.<env> (auto-created with a dev default if
# missing).

set -euo pipefail
ENV_NAME="${1:-dev}"
PROVISION_ONLY="false"
[[ "${2:-}" == "--provision-only" ]] && PROVISION_ONLY="true"
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../lib/db.sh
source "${ROOT_DIR}/scripts/lib/db.sh"

require_command python3

db_connection_env "${ENV_NAME}"
if [[ "${ENV_NAME}" != "dev" && "${ENV_NAME}" != "test" ]] && [[ -z "${DB_PASSWORD}" || "${DB_PASSWORD}" == "test123" || "${DB_PASSWORD}" == change-me* ]]; then
  echo "Refusing: set a real DATABASE_PASSWORD in .credentials.${ENV_NAME} first" >&2
  exit 1
fi

echo "==> [${ENV_NAME}] Provisioning role '${DB_USER}' and database '${DB_NAME}'"
TMP_SQL="$(mktemp)"
trap 'rm -f "${TMP_SQL}"' EXIT
render_setup_sql "${TMP_SQL}"
run_psql_superuser "${TMP_SQL}"

if [[ "${PROVISION_ONLY}" == "true" ]]; then
  echo "==> [${ENV_NAME}] Role and database ready; the containers migrate on start."
  exit 0
fi
require_command psql

echo "==> [${ENV_NAME}] Applying migrations"
APP_ENV="${ENV_NAME}" DATABASE_URL="${DATABASE_URL}" "${ROOT_DIR}/scripts/db/migrate.sh" "${ENV_NAME}"

echo "==> [${ENV_NAME}] Seeding billing plans"
APP_ENV="${ENV_NAME}" DATABASE_URL="${DATABASE_URL}" "${ROOT_DIR}/scripts/db/seed.sh" "${ENV_NAME}"

echo "==> [${ENV_NAME}] Database ready: ${DATABASE_URL/${DB_PASSWORD}/****}"
