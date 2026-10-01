#!/usr/bin/env bash
#
# db.sh — shared helpers for the database setup scripts.
#
# Resolves the DB identity from app.config.json (via config.sh) and the password
# from .credentials.<env>, renders the SQL template with safe identifier quoting,
# and applies it as the postgres superuser. Sourced by scripts/db/*.sh.

set -euo pipefail

_DB_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_DB_ROOT="$(cd "${_DB_LIB_DIR}/../.." && pwd)"
# shellcheck source=config.sh
source "${_DB_LIB_DIR}/config.sh"

require_command() {
  command -v "$1" >/dev/null 2>&1 || { echo "Required command not found: $1" >&2; exit 1; }
}

# read_credential <env> <KEY> [default] — pull a secret from .credentials.<env>.
read_credential() {
  local env_name="$1" key="$2" default="${3:-}"
  local file="${_DB_ROOT}/.credentials.${env_name}"
  if [[ -f "${file}" ]]; then
    local line; line="$(grep -E "^${key}=" "${file}" | tail -n1 || true)"
    if [[ -n "${line}" ]]; then echo "${line#*=}"; return 0; fi
  fi
  echo "${default}"
}

# db_connection_env <env> — export DB_NAME/DB_USER (from config) + DB_PASSWORD/
# DB_HOST/DB_PORT (from .credentials/.env), and a psql-ready DATABASE_URL.
db_connection_env() {
  local env_name="$1"
  load_app_config "${env_name}"                       # -> DB_NAME, DB_USER
  export DB_PASSWORD; DB_PASSWORD="$(read_credential "${env_name}" DATABASE_PASSWORD test123)"
  export DB_HOST;     DB_HOST="${POSTGRES_HOST:-127.0.0.1}"
  export DB_PORT;     DB_PORT="${POSTGRES_PORT:-5432}"
  export DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
}

# render_setup_sql <out_file> — substitute placeholders with proper quoting.
render_setup_sql() {
  local out="$1"
  local template="${_DB_ROOT}/scripts/db/setup-database.sql.template"
  DB_USER="${DB_USER}" DB_PASSWORD="${DB_PASSWORD}" DB_NAME="${DB_NAME}" \
  TEMPLATE="${template}" OUT="${out}" python3 - <<'PY'
import os
from pathlib import Path

def ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'

tpl = Path(os.environ["TEMPLATE"]).read_text(encoding="utf-8")
sql = (
    tpl.replace("{{DB_USER}}", os.environ["DB_USER"])
       .replace("{{DB_USER_IDENT}}", ident(os.environ["DB_USER"]))
       .replace("{{DB_PASSWORD}}", os.environ["DB_PASSWORD"].replace("'", "''"))
       .replace("{{DB_NAME}}", os.environ["DB_NAME"])
       .replace("{{DB_NAME_IDENT}}", ident(os.environ["DB_NAME"]))
)
Path(os.environ["OUT"]).write_text(sql, encoding="utf-8")
PY
}

# run_psql_superuser <sql_file> — apply SQL as the postgres superuser.
# Piped on stdin because a mktemp file in /tmp is mode 600 (postgres can't read it).
run_psql_superuser() {
  local sql_file="$1"
  if command -v sudo >/dev/null 2>&1 && id postgres >/dev/null 2>&1; then
    sudo -u postgres psql -v ON_ERROR_STOP=1 -f - < "${sql_file}"
  else
    psql -U postgres -v ON_ERROR_STOP=1 -f - < "${sql_file}"
  fi
}

# psql_app <sql> — run one statement as the app user against the app DB.
psql_app() {
  PGPASSWORD="${DB_PASSWORD}" psql -v ON_ERROR_STOP=1 \
    -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -c "$1"
}
