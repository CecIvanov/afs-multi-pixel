#!/usr/bin/env bash
#
# smoke.sh <uat|production> — after a start, check what Shopify and its reviewers
# hit: every container healthy, the API, the app root, /privacy and /terms over the
# public URL (through Caddy), and the webhook route refusing an unsigned request
# with 401 (not 404/500). Exits non-zero on any failure. Run on the VPS.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
stack="${1:?usage: smoke.sh <uat|production>}"
env_file="${ROOT_DIR}/.env.${stack}"
value() { grep -E "^$1=" "${env_file}" | tail -1 | cut -d= -f2-; }

app_url="$(value SHOPIFY_APP_URL)"
api_port="$(value API_PORT)"
prefix="${APP_IMAGE_PREFIX:-afsmultipixel}"
failed=0
ok()   { printf '  ok    %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1" >&2; failed=1; }

echo "==> Containers (waiting up to 120s for healthchecks)"
for service in api jobs worker ui redis; do
  name="${prefix}-${service}-${stack}"
  status=""
  for _ in $(seq 1 24); do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${name}" 2>/dev/null || echo missing)"
    [[ "${status}" == "healthy" || "${status}" == "running" ]] && break
    sleep 5
  done
  [[ "${status}" == "healthy" || "${status}" == "running" ]] && ok "${name}: ${status}" || fail "${name}: ${status}"
done

echo "==> API"
health="$(curl -fsS "http://127.0.0.1:${api_port}/api/v1/health" 2>/dev/null || true)"
[[ "${health}" == *'"status":"ok"'* ]] && ok "health ${health}" || fail "health: ${health:-no answer}"

echo "==> Public URL ${app_url}"
check() { # check <path> <expected status> [method] [text the body must contain]
  local path="$1" want="$2" method="${3:-GET}" needle="${4:-}" body code
  body="$(mktemp)"
  code="$(curl -sS -o "${body}" -w '%{http_code}' -X "${method}" "${app_url}${path}" || echo 000)"
  if [[ "${code}" != "${want}" ]]; then
    fail "${method} ${path} -> ${code} (want ${want})"
  elif [[ -n "${needle}" ]] && ! grep -q "${needle}" "${body}"; then
    fail "${method} ${path} -> ${code} but no \"${needle}\" in the page"
  else
    ok "${method} ${path} -> ${code}"
  fi
  rm -f "${body}"
}
check / 200 GET "AFS Multi Pixel"
check /privacy 200 GET "Privacy"
check /terms 200 GET "Terms"
check /webhooks/app/uninstalled 401 POST
check /webhooks/shop/redact 401 POST

if [[ "${failed}" -ne 0 ]]; then
  echo "Smoke check FAILED for ${stack}" >&2
  exit 1
fi
echo "Smoke check passed for ${stack}"
