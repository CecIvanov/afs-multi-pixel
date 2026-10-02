#!/usr/bin/env bash
#
# stack.sh — the shared body of scripts/{start,stop,logs}-<stack>.sh (sourced, not run).
#
# Each stack is SEPARATE (own Shopify app, database, containers, ports): see
# docker-compose.<stack>.yml + .env.<stack> + .credentials.<stack>. They coexist on
# one host because container names / images / volumes / project are suffixed with
# the stack and the ports differ. The API applies migrations on boot.

set -euo pipefail
_STACK_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=compose.sh
source "${_STACK_LIB_DIR}/compose.sh"

_env_port() { grep -E "^$2=" "${ROOT_DIR}/.env.$1" 2>/dev/null | tail -1 | cut -d= -f2; }

# start_stack <stack> — build and start the stack, then show where it listens.
start_stack() {
  local stack="$1" api_port ui_port
  echo "==> Building and starting the ${stack} stack..."
  compose_stack "${stack}" up -d --build
  compose_stack "${stack}" ps

  api_port="$(_env_port "${stack}" API_PORT)"; api_port="${api_port:-8000}"
  ui_port="$(_env_port "${stack}" UI_PORT)"; ui_port="${ui_port:-3000}"

  printf '\n%s stack is up — %s (images %s/*:%s, db %s):\n' \
    "${stack}" "${APP_NAME}" "${APP_IMAGE_PREFIX}" "${stack}" "${DB_NAME}"
  printf '  UI      http://127.0.0.1:%s\n' "${ui_port}"
  printf '  API     http://127.0.0.1:%s/api/v1/health\n' "${api_port}"
  printf '  Docs    http://127.0.0.1:%s/docs\n\n' "${api_port}"
  printf 'Logs:  ./scripts/logs-%s.sh [service]    Stop:  ./scripts/stop-%s.sh\n' "${stack}" "${stack}"
}

# stop_stack <stack> [--volumes] — stop the stack; --volumes also drops its
# volumes (dev: its Postgres data; every stack: its Redis data). UAT and
# production keep their data in the VPS's Postgres, which this never touches.
stop_stack() {
  local stack="$1"
  if [[ "${2:-}" == "--volumes" ]]; then
    compose_stack "${stack}" down -v
  else
    compose_stack "${stack}" down
  fi
}

# logs_stack <stack> [service...] — follow the stack's logs (all services, or some).
logs_stack() {
  local stack="$1"; shift
  compose_stack "${stack}" logs -f --tail=100 "$@"
}
