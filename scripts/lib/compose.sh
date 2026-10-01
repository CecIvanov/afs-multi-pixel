#!/usr/bin/env bash
# Docker Compose helpers. Load app identity from app.config.json, secrets from
# .credentials.<stack>, then run `docker compose` with the base + overlay files.

set -euo pipefail

_COMPOSE_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${_COMPOSE_LIB_DIR}/../.." && pwd)"
# shellcheck source=config.sh
source "${_COMPOSE_LIB_DIR}/config.sh"
# shellcheck source=credentials.sh
source "${_COMPOSE_LIB_DIR}/credentials.sh"

require_env_file() {
  local env_file="$1"
  if [[ ! -f "${env_file}" ]]; then
    echo "Missing ${env_file}" >&2
    echo "  cp .env.example $(basename "${env_file}")" >&2
    exit 1
  fi
}

# compose_stack <stack> <compose args...>
# Exports APP_* (from app.config.json) + secrets, then runs docker compose with
# the base file and the stack overlay.
compose_stack() {
  local stack="$1"; shift
  local env_file="${ROOT_DIR}/.env.${stack}"
  local overlay="${ROOT_DIR}/docker-compose.${stack}.yml"

  require_env_file "${env_file}"
  load_app_config "${stack}"           # exports APP_*, DB_NAME, DB_USER, ...
  export_stack_credentials "${stack}"  # exports DATABASE_PASSWORD, INTERNAL_API_KEY, ...

  local -a files=(-f "${ROOT_DIR}/docker-compose.yml")
  [[ -f "${overlay}" ]] && files+=(-f "${overlay}")

  docker compose --env-file "${env_file}" "${files[@]}" "$@"
}
