#!/usr/bin/env bash
#
# start-dev.sh — build and start the DEV stack (local; its own Postgres container).
# Settings: .env.dev   Secrets: .credentials.dev
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/start-stack.sh
source "${ROOT_DIR}/scripts/lib/start-stack.sh"
start_stack dev
