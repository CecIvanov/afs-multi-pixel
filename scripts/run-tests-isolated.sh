#!/usr/bin/env bash
#
# run-tests-isolated.sh — spin up a throwaway tmpfs Postgres, run the whole suite,
# tear it down. No shared/host database is ever touched.
#
#   ./scripts/run-tests-isolated.sh
#
# The DB name/user come from app.config.json (the test env -> <slug>_test); the
# ephemeral Postgres listens on 127.0.0.1:${TEST_DB_PORT:-5433}.

set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/config.sh
source "${ROOT_DIR}/scripts/lib/config.sh"

load_app_config test                 # exports DB_NAME (<slug>_test), DB_USER
export DB_NAME DB_USER APP_IMAGE_PREFIX
export TEST_DB_PORT="${TEST_DB_PORT:-5433}"
export TEST_DB_PASSWORD="${TEST_DB_PASSWORD:-test123}"

compose() { docker compose -f "${ROOT_DIR}/docker-compose.test.yml" "$@"; }

cleanup() { compose down -v >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "==> Starting ephemeral Postgres (${DB_NAME} on 127.0.0.1:${TEST_DB_PORT})"
compose up -d

echo "==> Waiting for Postgres to be healthy"
for _ in $(seq 1 30); do
  status="$(compose ps --format '{{.Health}}' postgres-test 2>/dev/null || true)"
  [[ "${status}" == "healthy" ]] && break
  sleep 1
done

export TEST_DATABASE_URL="postgresql://${DB_USER}:${TEST_DB_PASSWORD}@127.0.0.1:${TEST_DB_PORT}/${DB_NAME}"
"${ROOT_DIR}/scripts/run-tests.sh"
