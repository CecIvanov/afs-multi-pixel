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
  set -a
  # shellcheck disable=SC1090
  source "${_CRED_ROOT}/.credentials.${stack}"
  set +a
}
