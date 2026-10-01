#!/usr/bin/env bash
#
# run-tests.sh — run the full suite against an ALREADY-AVAILABLE test database.
#
#   TEST_DATABASE_URL=postgresql://user@host:port/name_test ./scripts/run-tests.sh
#
# Applies migrations, runs Python (pytest) + Node (node --test). Used directly in
# CI (where a Postgres service is provisioned) and by run-tests-isolated.sh (which
# spins up a throwaway Postgres first). Override the interpreter with PYTHON=...

set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3}"

: "${TEST_DATABASE_URL:?set TEST_DATABASE_URL to a *_test database}"
if [[ "${TEST_DATABASE_URL##*/}" != *test* ]]; then
  echo "Refusing: TEST_DATABASE_URL must point at a *_test database" >&2
  exit 1
fi

export DATABASE_URL="${TEST_DATABASE_URL}"
export APP_CONFIG_PATH="${APP_CONFIG_PATH:-${ROOT_DIR}/app.config.json}"
export PYTHONPATH="${ROOT_DIR}/backend:${ROOT_DIR}/packages"

echo "==> Applying migrations"
( cd "${ROOT_DIR}/backend" && "${PYTHON}" -m alembic upgrade head )

echo "==> Python tests (pytest)"
( cd "${ROOT_DIR}/backend" && "${PYTHON}" -m pytest -q )

echo "==> Node tests (node --test)"
( cd "${ROOT_DIR}/shopify" && npm test )

echo "All tests passed."
