#!/usr/bin/env bash
#
# logs.sh — tail one environment's logs (optionally a single service).
#
#   ./scripts/logs.sh              # all dev services
#   ./scripts/logs.sh uat api      # just the uat api service

set -euo pipefail
ENV_NAME="${1:-dev}"; shift || true
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/compose.sh
source "${ROOT_DIR}/scripts/lib/compose.sh"

compose_stack "${ENV_NAME}" logs -f --tail=100 "$@"
