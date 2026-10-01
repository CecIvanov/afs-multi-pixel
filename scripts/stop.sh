#!/usr/bin/env bash
#
# stop.sh — stop one environment's stack. Add --volumes to drop its DB/Redis data.
#
#   ./scripts/stop.sh              # dev
#   ./scripts/stop.sh uat
#   ./scripts/stop.sh prd --volumes

set -euo pipefail
ENV_NAME="${1:-dev}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/compose.sh
source "${ROOT_DIR}/scripts/lib/compose.sh"

if [[ "${2:-}" == "--volumes" ]]; then
  compose_stack "${ENV_NAME}" down -v
else
  compose_stack "${ENV_NAME}" down
fi
