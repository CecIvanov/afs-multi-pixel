#!/usr/bin/env bash
#
# backup.sh — nightly Postgres dump of one stack, kept 14 days, copied off the VPS
# (spec §8).
#
#   ./scripts/db/backup.sh uat          # or production
#
# Writes <BACKUP_DIR>/<db>-<UTC timestamp>.dump (pg_dump custom format), deletes
# local dumps older than BACKUP_RETENTION_DAYS (14), and, when BACKUP_REMOTE is set
# (an rclone remote path such as "b2:afs-backups/uat"), copies the dump there and
# prunes remote dumps older than the same retention. pg_dump runs in the
# postgres:16-alpine image, so the host needs only Docker (and rclone for the
# off-VPS copy). DATABASE_URL in the environment overrides the stack's database.
#
# Cron (on the VPS, as the deploy user):
#   15 2 * * * cd /srv/afs-multi-pixel && ./scripts/db/backup.sh production >> /var/log/afs-backup-production.log 2>&1

set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../lib/db.sh
source "${ROOT_DIR}/scripts/lib/db.sh"

ENV_NAME="${1:?usage: backup.sh <uat|production|dev>}"
if [[ -z "${DATABASE_URL:-}" ]]; then
  db_connection_env "${ENV_NAME}"
fi
BACKUP_DIR="${BACKUP_DIR:-/var/backups/afsmultipixel/${ENV_NAME}}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DB_LABEL="${DATABASE_URL##*/}"
DUMP="${BACKUP_DIR}/${DB_LABEL%%\?*}-${STAMP}.dump"

mkdir -p "${BACKUP_DIR}"
echo "==> Dumping ${DB_LABEL} to ${DUMP}"
docker run --rm --network host -v "${BACKUP_DIR}:/backup" postgres:16-alpine \
  pg_dump --format=custom --no-owner --file="/backup/$(basename "${DUMP}")" "${DATABASE_URL}"
[[ -s "${DUMP}" ]] || { echo "Dump is empty: ${DUMP}" >&2; exit 1; }

echo "==> Pruning local dumps older than ${RETENTION_DAYS} days"
find "${BACKUP_DIR}" -name '*.dump' -type f -mtime "+${RETENTION_DAYS}" -print -delete

if [[ -n "${BACKUP_REMOTE:-}" ]]; then
  require_command rclone
  echo "==> Copying to ${BACKUP_REMOTE}"
  rclone copy "${DUMP}" "${BACKUP_REMOTE}"
  rclone delete --min-age "${RETENTION_DAYS}d" --include '*.dump' "${BACKUP_REMOTE}"
else
  echo "!! BACKUP_REMOTE is not set: the dump stays on this VPS only" >&2
fi
echo "==> Backup done: ${DUMP}"
