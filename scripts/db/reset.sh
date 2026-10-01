#!/usr/bin/env bash
#
# reset.sh — DROP and recreate the database for a NON-PRODUCTION environment.
#
#   ./scripts/db/reset.sh [dev|test]                  (default: dev)
#
# Destructive. Guarded three ways: production is refused outright, the target DB
# name must carry the env suffix, and (for anything but the test sentinel) an
# interactive confirmation is required. After dropping it re-runs the full setup.

set -euo pipefail
ENV_NAME="${1:-dev}"
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../lib/db.sh
source "${ROOT_DIR}/scripts/lib/db.sh"

if [[ "${ENV_NAME}" == "prod" || "${ENV_NAME}" == "production" ]]; then
  echo "Refusing to reset a production database." >&2
  exit 1
fi

db_connection_env "${ENV_NAME}"

# Guard: the target must be an env-suffixed database, never a bare prod name.
if [[ "${DB_NAME}" != *"_${ENV_NAME}" ]]; then
  echo "Refusing: '${DB_NAME}' does not look like a ${ENV_NAME} database." >&2
  exit 1
fi

# Non-test resets require explicit confirmation.
if [[ "${DB_NAME}" != "${APP_TEST_DB_SENTINEL}" ]]; then
  read -r -p "Drop and recreate '${DB_NAME}'? Type the database name to confirm: " reply
  if [[ "${reply}" != "${DB_NAME}" ]]; then
    echo "Aborted." >&2
    exit 1
  fi
fi

echo "==> Dropping database '${DB_NAME}'"
DROP_SQL="$(mktemp)"
trap 'rm -f "${DROP_SQL}"' EXIT
printf 'DROP DATABASE IF EXISTS %s WITH (FORCE);\n' "\"${DB_NAME}\"" > "${DROP_SQL}"
run_psql_superuser "${DROP_SQL}"

echo "==> Recreating '${DB_NAME}'"
"${ROOT_DIR}/scripts/db/setup.sh" "${ENV_NAME}"
