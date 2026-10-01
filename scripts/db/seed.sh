#!/usr/bin/env bash
#
# seed.sh — seed the billing plan catalog from app.config.json.
#
#   ./scripts/db/seed.sh [dev|test|staging|prod]      (default: dev)
#
# Reads billing.plans from the single config file and upserts them into
# billing_plans (idempotent: ON CONFLICT (handle) DO UPDATE). This is the local
# mirror of the plans you define in the Shopify Partner Dashboard; `shopifyPlanName`
# is what lets a live subscription normalize back to a handle.
#
# Skips cleanly if the billing_plans table does not exist yet (backend not migrated).

set -euo pipefail
ENV_NAME="${1:-dev}"
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../lib/db.sh
source "${ROOT_DIR}/scripts/lib/db.sh"

if [[ -z "${DATABASE_URL:-}" ]]; then
  db_connection_env "${ENV_NAME}"
fi

# Does billing_plans exist? If not, the backend hasn't been migrated yet.
HAS_TABLE="$(PGPASSWORD="${DB_PASSWORD}" psql -tA \
  -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
  -c "SELECT to_regclass('public.billing_plans') IS NOT NULL;" 2>/dev/null || echo f)"

if [[ "${HAS_TABLE}" != "t" ]]; then
  echo "  - Seed: skipped (billing_plans table not present yet — run migrations first)"
  exit 0
fi

# Render the plan rows from app.config.json into an idempotent upsert.
SEED_SQL="$(APP_CONFIG_PATH="${ROOT_DIR}/app.config.json" python3 - <<'PY'
import json, os

cfg = json.load(open(os.environ["APP_CONFIG_PATH"], encoding="utf-8"))
plans = cfg.get("billing", {}).get("plans", [])

def sql_str(v):
    return "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"

def sql_num(v):
    return "NULL" if v is None else str(int(v))

rows = []
for p in plans:
    rows.append(
        "({handle}, {name}, {quota}, {shopify})".format(
            handle=sql_str(p["handle"]),
            name=sql_str(p.get("name", p["handle"])),
            quota=sql_num(p.get("monthlyQuota")),
            shopify=sql_str(p.get("shopifyPlanName")),
        )
    )

if not rows:
    print("SELECT 1;")
else:
    print(
        "INSERT INTO billing_plans (handle, name, monthly_quota, shopify_plan_name)\n"
        "VALUES\n  " + ",\n  ".join(rows) + "\n"
        "ON CONFLICT (handle) DO UPDATE SET\n"
        "  name = EXCLUDED.name,\n"
        "  monthly_quota = EXCLUDED.monthly_quota,\n"
        "  shopify_plan_name = EXCLUDED.shopify_plan_name;"
    )
PY
)"

echo "  - Seed: upserting $(echo "${SEED_SQL}" | grep -c '^  (' || true) plan(s)"
psql_app "${SEED_SQL}"
