#!/usr/bin/env bash
#
# logs-production.sh — follow the production stack's logs:  ./scripts/logs-production.sh [api|jobs|worker|beat|ui|redis]
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/stack.sh
source "${ROOT_DIR}/scripts/lib/stack.sh"
logs_stack production "$@"
