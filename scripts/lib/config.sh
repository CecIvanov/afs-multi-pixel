#!/usr/bin/env bash
#
# config.sh — the single source of truth for app identity, for shell/Docker.
#
# Reads app.config.json (via python3, no jq dependency) and exports the derived
# environment variables that docker-compose, the DB scripts and the start
# scripts all consume. Source it, then call `load_app_config [env]`.
#
#   source scripts/lib/config.sh
#   load_app_config dev
#   echo "$APP_NAME"      -> the human name from app.config.json
#   echo "$DB_NAME"       -> myapp_dev
#
# Exported:  APP_NAME APP_HANDLE APP_SLUG APP_PRIMARY_LOCALE APP_SUPPORT_EMAIL
#            APP_IMAGE_PREFIX APP_SHARED_NETWORK APP_CELERY_KEY_PREFIX
#            APP_TEST_DB_SENTINEL SHOPIFY_API_VERSION
#            DB_NAME DB_USER   (derived from the env argument)

set -euo pipefail

_config_repo_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
}

# _config_get <dotted.path> [default] — read one value from app.config.json.
_config_get() {
  local path="$1" default="${2:-}"
  local root; root="$(_config_repo_root)"
  APP_CONFIG_PATH="${APP_CONFIG_PATH:-${root}/app.config.json}" \
  CFG_PATH="${path}" CFG_DEFAULT="${default}" python3 - <<'PY'
import json, os, sys
cfg = json.load(open(os.environ["APP_CONFIG_PATH"], encoding="utf-8"))
cur = cfg
for part in os.environ["CFG_PATH"].split("."):
    if isinstance(cur, dict) and part in cur:
        cur = cur[part]
    else:
        cur = None
        break
if cur is None:
    sys.stdout.write(os.environ.get("CFG_DEFAULT", ""))
elif isinstance(cur, bool):
    sys.stdout.write("true" if cur else "false")
elif isinstance(cur, (str, int, float)):
    sys.stdout.write(str(cur))
else:
    sys.stdout.write(json.dumps(cur))
PY
}

# load_app_config [env]  — env defaults to $APP_ENV or "dev".
load_app_config() {
  local env_name="${1:-${APP_ENV:-dev}}"

  export APP_NAME;            APP_NAME="$(_config_get app.name 'My Shopify App')"
  export APP_HANDLE;          APP_HANDLE="$(_config_get app.handle 'my-shopify-app')"
  export APP_SLUG;            APP_SLUG="$(_config_get app.slug 'myapp')"
  export APP_PRIMARY_LOCALE;  APP_PRIMARY_LOCALE="$(_config_get app.primaryLocale en)"
  export APP_SUPPORT_EMAIL;   APP_SUPPORT_EMAIL="$(_config_get app.supportEmail '')"

  # Identity derivatives default to the slug; app.config.json may override each.
  export APP_IMAGE_PREFIX;      APP_IMAGE_PREFIX="$(_config_get identifiers.imagePrefix "${APP_SLUG}")"
  export APP_SHARED_NETWORK;    APP_SHARED_NETWORK="$(_config_get identifiers.sharedNetwork "${APP_SLUG}-shared")"
  export APP_CELERY_KEY_PREFIX; APP_CELERY_KEY_PREFIX="$(_config_get identifiers.celeryKeyPrefix "${APP_SLUG}")"
  export APP_TEST_DB_SENTINEL;  APP_TEST_DB_SENTINEL="$(_config_get identifiers.testDbSentinel "${APP_SLUG}_test")"
  export SHOPIFY_API_VERSION;   SHOPIFY_API_VERSION="$(_config_get shopify.apiVersion 2025-10)"

  # Support channels (Help page + optional Viber floating button).
  export SUPPORT_EMAIL;          SUPPORT_EMAIL="$(_config_get support.email '')"
  export SUPPORT_VIBER_ENABLED;  SUPPORT_VIBER_ENABLED="$(_config_get support.viber.enabled false)"
  export SUPPORT_VIBER_NUMBER;   SUPPORT_VIBER_NUMBER="$(_config_get support.viber.numberE164 '')"
  export SUPPORT_VIBER_DISPLAY;  SUPPORT_VIBER_DISPLAY="$(_config_get support.viber.display '')"
  export SUPPORT_VIBER_LABEL;    SUPPORT_VIBER_LABEL="$(_config_get support.viber.label 'Chat on Viber')"

  local db_name_prefix db_user_prefix
  db_name_prefix="$(_config_get identifiers.databaseNamePrefix "${APP_SLUG}")"
  db_user_prefix="$(_config_get identifiers.databaseUserPrefix "${APP_SLUG}")"

  # Production uses the bare prefix; every other env is suffixed (matches the
  # myapp_dev / myapp_test / myapp convention).
  if [[ "${env_name}" == "prod" || "${env_name}" == "production" ]]; then
    export DB_NAME="${db_name_prefix}"
    export DB_USER="${db_user_prefix}"
  else
    export DB_NAME="${db_name_prefix}_${env_name}"
    export DB_USER="${db_user_prefix}_${env_name}"
  fi
}
