#!/usr/bin/env bash
#
# logs-dev.sh — follow the dev stack's logs:  ./scripts/logs-dev.sh [api|jobs|worker|beat|ui|redis]
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/stack.sh
source "${ROOT_DIR}/scripts/lib/stack.sh"
logs_stack dev "$@"
