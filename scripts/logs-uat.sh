#!/usr/bin/env bash
#
# logs-uat.sh — follow the uat stack's logs:  ./scripts/logs-uat.sh [api|jobs|worker|beat|ui|redis]
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/stack.sh
source "${ROOT_DIR}/scripts/lib/stack.sh"
logs_stack uat "$@"
