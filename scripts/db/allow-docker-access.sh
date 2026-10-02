#!/usr/bin/env bash
#
# allow-docker-access.sh — let this app's containers reach the VPS's own Postgres.
#
#   ./scripts/db/allow-docker-access.sh uat production     (on the VPS, needs sudo)
#
# The UAT and production containers connect to host.docker.internal:5432, which
# docker-compose maps to the host's Docker bridge gateway (172.17.0.1 by default).
# Their connections arrive from Docker bridge addresses (172.16.0.0/12), so:
#   1. pg_hba.conf needs a line per stack allowing its database + role from there
#      (added here, idempotently, then Postgres is reloaded);
#   2. Postgres must listen on the bridge (listen_addresses) — checked here, not
#      changed: if another app on this VPS already reaches Postgres the same way
#      (BG Delivery does), it already does.
# The database and role names come from app.config.json (scripts/lib/config.sh).

set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../lib/config.sh
source "${ROOT_DIR}/scripts/lib/config.sh"

[[ $# -gt 0 ]] || { echo "usage: allow-docker-access.sh <uat|production> [...]" >&2; exit 1; }
command -v sudo >/dev/null || { echo "sudo is required" >&2; exit 1; }
DOCKER_CIDR="${DOCKER_CIDR:-172.16.0.0/12}"
pg() { sudo -u postgres psql -tAc "$1" | tr -d '[:space:]'; }

PG_HBA="$(pg "SHOW hba_file")"
[[ -f "${PG_HBA}" ]] || { echo "Can't find pg_hba.conf (got '${PG_HBA}')" >&2; exit 1; }
echo "==> pg_hba.conf: ${PG_HBA}"

added=0
for stack in "$@"; do
  load_app_config "${stack}"   # -> DB_NAME, DB_USER
  entry="host    ${DB_NAME}    ${DB_USER}    ${DOCKER_CIDR}    scram-sha-256"
  if sudo grep -qF "${entry}" "${PG_HBA}"; then
    echo "  already there: ${entry}"
  else
    echo "${entry}" | sudo tee -a "${PG_HBA}" >/dev/null
    echo "  added:         ${entry}"
    added=$((added + 1))
  fi
done

if [[ "${added}" -gt 0 ]]; then
  echo "==> Reloading Postgres"
  sudo systemctl reload postgresql || sudo -u postgres psql -tAc "SELECT pg_reload_conf()" >/dev/null
fi

LISTEN="$(sudo -u postgres psql -tAc "SHOW listen_addresses")"
BRIDGE="$(ip -4 addr show docker0 2>/dev/null | awk '/inet /{sub("/.*","",$2); print $2}')"
BRIDGE="${BRIDGE:-172.17.0.1}"
echo "==> listen_addresses = '${LISTEN}' (Docker bridge gateway: ${BRIDGE})"
if [[ "${LISTEN}" != *"*"* && "${LISTEN}" != *"${BRIDGE}"* && "${LISTEN}" != *"0.0.0.0"* ]]; then
  cat >&2 <<MSG
!! Postgres doesn't listen on the Docker bridge, so containers can't connect.
   Set in postgresql.conf:  listen_addresses = 'localhost,${BRIDGE}'
   then: sudo systemctl restart postgresql   (a restart, not a reload)
   Keep port 5432 closed to the internet in the firewall.
MSG
  exit 1
fi
echo "==> Done. Containers can connect to host.docker.internal:5432."
