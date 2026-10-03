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
# BEFORE `docker compose --env-file`. Refuses to start when the file would
# silently break the stack (check_stack_credentials).
export_stack_credentials() {
  local stack="$1"
  require_credentials_file "${stack}" || return 1
  check_stack_credentials "${stack}" || return 1
  set -a
  # shellcheck disable=SC1090
  source "${_CRED_ROOT}/.credentials.${stack}"
  set +a
}

# _env_keys <file> — the KEY of every KEY=value line.
_env_keys() {
  grep -E '^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*=' "$1" 2>/dev/null | sed -E 's/^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)=.*/\1/' | sort -u
}

# _env_value <file> <KEY> — the last value of KEY (quotes stripped), or nothing.
_env_value() {
  grep -E "^[[:space:]]*$2=" "$1" 2>/dev/null | tail -1 | cut -d= -f2- | sed -E "s/^[\"']//; s/[\"']\$//" || true
}

# check_stack_credentials <stack>
#  1. No key of .credentials.<stack> may also be in .env.<stack>: the shell
#     environment wins over `docker compose --env-file`, so a leftover (often
#     empty) line here would override the real value there — e.g. an empty
#     SHOPIFY_APP_GID turns the Partner API off and no shop gets its plan.
#  2. UAT and production need every secret set (production also the Partner API
#     token when billing is managed).
check_stack_credentials() {
  local stack="$1"
  local creds="${_CRED_ROOT}/.credentials.${stack}" env_file="${_CRED_ROOT}/.env.${stack}"
  local failed=0 key

  if [[ -f "${env_file}" ]]; then
    local env_keys; env_keys="$(_env_keys "${env_file}")"
    for key in $(_env_keys "${creds}"); do
      if grep -qx "${key}" <<<"${env_keys}"; then
        echo "${key} is set in .env.${stack}: remove it from .credentials.${stack} (it would override that value)" >&2
        failed=1
      fi
    done
  fi

  if [[ "${stack}" == "uat" || "${stack}" == "production" ]]; then
    local -a required=(DATABASE_PASSWORD INTERNAL_API_KEY SHOPIFY_API_SECRET TOKEN_ENC_KEY)
    local billing_mode; billing_mode="$(_env_value "${env_file}" SHOPIFY_BILLING_MODE)"
    [[ "${billing_mode:-managed}" == "managed" ]] && required+=(SHOPIFY_PARTNER_ACCESS_TOKEN)
    for key in "${required[@]}"; do
      if [[ -z "$(_env_value "${creds}" "${key}")" ]]; then
        echo "${key} is missing or empty in .credentials.${stack}" >&2
        failed=1
      fi
    done
  fi

  return "${failed}"
}
