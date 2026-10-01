#!/usr/bin/env bash
#
# migrate.sh — apply schema migrations for both migration histories.
#
#   ./scripts/db/migrate.sh [dev|test|staging|prod]   (default: dev)
#
# Backend (Alembic/SQLAlchemy) owns every domain table; Shopify (Prisma) owns the
# OAuth `Session` table only. They share one database with separate histories, so
# each is migrated with its own tool. Steps whose service is not scaffolded yet
# are skipped with a note, so this is safe to run at any phase of the template.

set -euo pipefail
ENV_NAME="${1:-dev}"
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../lib/db.sh
source "${ROOT_DIR}/scripts/lib/db.sh"

# DATABASE_URL may be inherited from setup.sh; otherwise resolve it here.
if [[ -z "${DATABASE_URL:-}" ]]; then
  db_connection_env "${ENV_NAME}"
fi

# --- Backend: Alembic -------------------------------------------------------
if [[ -f "${ROOT_DIR}/backend/alembic.ini" ]]; then
  echo "  - Alembic: upgrade head"
  ( cd "${ROOT_DIR}/backend" && DATABASE_URL="${DATABASE_URL}" alembic upgrade head )
else
  echo "  - Alembic: skipped (backend/alembic.ini not present yet)"
fi

# --- Shopify: Prisma --------------------------------------------------------
if [[ -f "${ROOT_DIR}/shopify/prisma/schema.prisma" ]]; then
  echo "  - Prisma: migrate deploy"
  ( cd "${ROOT_DIR}/shopify" && DATABASE_URL="${DATABASE_URL}" npx prisma migrate deploy )
else
  echo "  - Prisma: skipped (shopify/prisma/schema.prisma not present yet)"
fi
