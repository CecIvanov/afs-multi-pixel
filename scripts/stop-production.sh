#!/usr/bin/env bash
#
# stop-production.sh — stop the production stack. --volumes also drops its Docker volumes
# (Redis data; on dev also its Postgres data). The VPS's Postgres is never touched.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/stack.sh
source "${ROOT_DIR}/scripts/lib/stack.sh"
stop_stack production "$@"
