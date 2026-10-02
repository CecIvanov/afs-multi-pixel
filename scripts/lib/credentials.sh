#!/usr/bin/env bash
# Secrets loading for the compose helpers.

set -euo pipefail

_CRED_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_CRED_ROOT="$(cd "${_CRED_LIB_DIR}/../.." && pwd)"

require_credentials_file() {
  local stack="$1"
  local file="${_CRED_ROOT}/.credentials.${stack}"
  if [[ ! -f "${file}" ]]; then
    echo "Missing ${file}" >&2
    echo "  cp .credentials.example .credentials.${stack}   # then edit the secrets" >&2
    return 1
  fi
}

# export_stack_credentials <stack> — source .credentials.<stack> so ${VAR}
# references in .env.<stack> and docker-compose interpolation resolve. Must run
# BEFORE `docker compose --env-file`.
export_stack_credentials() {
  local stack="$1"
  require_credentials_file "${stack}" || return 1
  # The client ID moved to .env.<stack>; a leftover (often empty) line here would
  # override it, since the shell environment wins over docker compose --env-file.
  if grep -qE '^[[:space:]]*SHOPIFY_API_KEY=' "${_CRED_ROOT}/.credentials.${stack}"; then
    echo "SHOPIFY_API_KEY now lives in .env.${stack}: remove it from .credentials.${stack}" >&2
    return 1
  fi
  set -a
  # shellcheck disable=SC1090
  source "${_CRED_ROOT}/.credentials.${stack}"
  set +a
}
