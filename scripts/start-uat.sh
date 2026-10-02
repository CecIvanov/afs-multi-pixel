#!/usr/bin/env bash
#
# start-uat.sh — build and start the UAT stack (the UAT App, a custom app; VPS Black, host Postgres).
# Settings: .env.uat   Secrets: .credentials.uat
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/start-stack.sh
source "${ROOT_DIR}/scripts/lib/start-stack.sh"
start_stack uat
