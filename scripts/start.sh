#!/usr/bin/env bash
#
# start.sh — bring up a full stack for one environment.
#
#   ./scripts/start.sh            # dev (default)
#   ./scripts/start.sh uat
#   ./scripts/start.sh production
#
# Each env is a SEPARATE stack (own Shopify app, database, containers, ports) —
# see docker-compose.<env>.yml + .env.<env> + .credentials.<env>. They coexist on
# one host because container names / images / volumes / project are suffixed with
# the env and the ports differ. The API applies migrations on boot.

set -euo pipefail
ENV_NAME="${1:-dev}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/compose.sh
source "${ROOT_DIR}/scripts/lib/compose.sh"

echo "==> Building and starting the ${ENV_NAME} stack..."
compose_stack "${ENV_NAME}" up -d --build
compose_stack "${ENV_NAME}" ps

env_port() { grep -E "^$1=" "${ROOT_DIR}/.env.${ENV_NAME}" 2>/dev/null | tail -1 | cut -d= -f2; }
API_PORT="$(env_port API_PORT)"; API_PORT="${API_PORT:-8000}"
UI_PORT="$(env_port UI_PORT)"; UI_PORT="${UI_PORT:-3000}"

cat <<EOF

${ENV_NAME} stack is up — ${APP_NAME} (images ${APP_IMAGE_PREFIX}/*:${ENV_NAME}, db ${DB_NAME}):
  UI      http://127.0.0.1:${UI_PORT}
  API     http://127.0.0.1:${API_PORT}/api/v1/health
  Docs    http://127.0.0.1:${API_PORT}/docs

Logs:  ./scripts/logs.sh ${ENV_NAME}    Stop:  ./scripts/stop.sh ${ENV_NAME}
EOF
