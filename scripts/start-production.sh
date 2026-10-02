#!/usr/bin/env bash
#
# start-production.sh — build and start the PRODUCTION stack (the Production App; VPS Black, host Postgres).
# Settings: .env.production   Secrets: .credentials.production
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/start-stack.sh
source "${ROOT_DIR}/scripts/lib/start-stack.sh"
start_stack production
