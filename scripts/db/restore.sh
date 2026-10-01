#!/usr/bin/env bash
#
# restore.sh — restore a backup.sh dump into an EMPTY database.
#
#   TARGET_DATABASE_URL=postgresql://user:pass@host:port/db ./scripts/db/restore.sh <file.dump>
#
# Refuses a target that already has tables, so it can't overwrite a live database
# by accident. Create the empty database (and role) first, e.g. with
# scripts/db/setup.sh on a fresh server. Runs pg_restore in postgres:16-alpine.

set -euo pipefail
DUMP="${1:?usage: restore.sh <file.dump>}"
: "${TARGET_DATABASE_URL:?set TARGET_DATABASE_URL to the empty database to restore into}"
[[ -s "${DUMP}" ]] || { echo "No such dump: ${DUMP}" >&2; exit 1; }

DIR="$(cd "$(dirname "${DUMP}")" && pwd)"
pg() { docker run --rm --network host -v "${DIR}:/backup" postgres:16-alpine "$@"; }

TABLES="$(pg psql "${TARGET_DATABASE_URL}" -tAc "select count(*) from information_schema.tables where table_schema = 'public'")"
if [[ "${TABLES}" != "0" ]]; then
  echo "Refusing: the target database already has ${TABLES} tables" >&2
  exit 1
fi

echo "==> Restoring $(basename "${DUMP}")"
pg pg_restore --no-owner --exit-on-error --dbname="${TARGET_DATABASE_URL}" "/backup/$(basename "${DUMP}")"
echo "==> Restored. Tables: $(pg psql "${TARGET_DATABASE_URL}" -tAc "select count(*) from information_schema.tables where table_schema = 'public'")"
