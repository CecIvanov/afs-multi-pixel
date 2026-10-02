#!/usr/bin/env bash
#
# start-production.sh — build and start the PRODUCTION stack (the Production App; VPS Black, host Postgres).
# Settings: .env.production   Secrets: .credentials.production
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/stack.sh
source "${ROOT_DIR}/scripts/lib/stack.sh"
start_stack production
