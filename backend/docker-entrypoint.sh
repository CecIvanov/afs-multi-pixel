#!/bin/bash
set -euo pipefail

run_migrations() {
  local max_attempts="${MIGRATION_MAX_ATTEMPTS:-30}"
  local attempt=1
  until alembic upgrade head; do
    if [[ "${attempt}" -ge "${max_attempts}" ]]; then
      echo "Database migrations failed after ${max_attempts} attempts" >&2
      exit 1
    fi
    echo "Waiting for database before migrations (${attempt}/${max_attempts})..."
    sleep 2
    attempt=$((attempt + 1))
  done
  echo "Database migrations applied."
}

prepare_prometheus_multiprocess() {
  if [[ -n "${PROMETHEUS_MULTIPROC_DIR:-}" ]]; then
    rm -rf "${PROMETHEUS_MULTIPROC_DIR}"
    mkdir -p "${PROMETHEUS_MULTIPROC_DIR}"
    echo "Prepared Prometheus multiprocess dir: ${PROMETHEUS_MULTIPROC_DIR}"
  fi
}

# Only the migration-owning service (uvicorn, RUN_DB_MIGRATIONS!=false) migrates,
# so worker/beat containers never race on Alembic at boot.
if [[ "${1:-}" == "uvicorn" && "${RUN_DB_MIGRATIONS:-true}" == "true" ]]; then
  run_migrations
fi

prepare_prometheus_multiprocess

exec "$@"
