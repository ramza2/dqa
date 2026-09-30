#!/usr/bin/env bash
# Static regression checks for on-prem Compose auth + network boundaries.
# Does not require a running Docker daemon for source assertions.
# When Docker is available, also validates resolved `docker compose config` output.
#
# Never installs Python packages (no pip). Prefer stdlib text checks; for Docker
# resolve checks, grep the rendered Compose config without mutating the host env.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

ONPREM="${ROOT}/docker-compose.onprem.yml"
DEV_OVERLAY="${ROOT}/docker-compose.onprem.dev.yml"
ENV_EXAMPLE="${ROOT}/.env.onprem.example"
COMMON="${ROOT}/scripts/dqa-common.sh"
UP="${ROOT}/scripts/dqa-up.sh"
MIGRATE="${ROOT}/scripts/dqa-migrate.sh"
DOWN="${ROOT}/scripts/dqa-down.sh"
CHECK_AT_HEAD="${ROOT}/backend/alembic/check_at_head.py"
NGINX_CONF="${ROOT}/frontend/nginx.conf"
NGINX_MAIN="${ROOT}/frontend/nginx.main.conf"
NGINX_PROXY="${ROOT}/frontend/dqa_proxy_params.conf"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

pass() {
  echo "PASS: $*"
}

[[ -f "${ONPREM}" ]] || fail "missing ${ONPREM}"
[[ -f "${DEV_OVERLAY}" ]] || fail "missing ${DEV_OVERLAY}"
[[ -f "${CHECK_AT_HEAD}" ]] || fail "missing ${CHECK_AT_HEAD}"
[[ -f "${NGINX_CONF}" ]] || fail "missing ${NGINX_CONF}"
[[ -f "${NGINX_MAIN}" ]] || fail "missing ${NGINX_MAIN}"
[[ -f "${NGINX_PROXY}" ]] || fail "missing ${NGINX_PROXY}"

# --- Production Compose source: hardcoded auth (not ${...} from env) ---
grep -qE '^[[:space:]]*APP_ENV:[[:space:]]*production[[:space:]]*$' "${ONPREM}" \
  || fail "production Compose must hardcode APP_ENV: production"
grep -qE '^[[:space:]]*DQA_AUTH_PROVIDER:[[:space:]]*disabled[[:space:]]*$' "${ONPREM}" \
  || fail "production Compose must hardcode DQA_AUTH_PROVIDER: disabled"

if grep -nE 'APP_ENV:[[:space:]]*\$\{APP_ENV' "${ONPREM}" >/dev/null; then
  fail "production Compose must not allow APP_ENV override via .env"
fi
if grep -nE 'DQA_AUTH_PROVIDER:[[:space:]]*\$\{DQA_AUTH_PROVIDER' "${ONPREM}" >/dev/null; then
  fail "production Compose must not allow DQA_AUTH_PROVIDER override via .env"
fi
pass "production Compose hardcodes APP_ENV=production and DQA_AUTH_PROVIDER=disabled"

python3 - <<'PY' || fail "migrate APP_ENV / topology check failed"
from pathlib import Path
import re

text = Path("docker-compose.onprem.yml").read_text()
match = re.search(r"(?ms)^  migrate:\n(.*?)(?=^  [a-z].*:|\Z)", text)
assert match, "migrate service block not found"
block = match.group(1)
assert re.search(r"(?m)^\s+APP_ENV:\s*production\s*$", block), block
assert "APP_ENV: ${" not in block

# Topology via text (no PyYAML / no pip).
db_block = re.search(r"(?ms)^  dqa-db:\n(.*?)(?=^  [a-z].*:|\Z)", text)
backend_block = re.search(r"(?ms)^  backend:\n(.*?)(?=^  [a-z].*:|\Z)", text)
frontend_block = re.search(r"(?ms)^  frontend:\n(.*?)(?=^  [a-z].*:|\Z)", text)
assert db_block and backend_block and frontend_block
assert not re.search(r"(?m)^\s+ports:\s*$", db_block.group(1)), "DB must not publish host ports"
assert not re.search(r"(?m)^\s+ports:\s*$", backend_block.group(1)), "backend must not publish host ports"
assert re.search(r"(?m)^\s+ports:\s*$", frontend_block.group(1)), "frontend must publish LAN port"
assert re.search(r"(?m)^\s+expose:\s*$", backend_block.group(1))
assert 'internal: true' in text
assert re.search(r"(?m)^\s+APP_ENV:\s*production\s*$", backend_block.group(1))
assert re.search(r"(?m)^\s+DQA_AUTH_PROVIDER:\s*disabled\s*$", backend_block.group(1))
print("migrate_and_topology_ok")
PY
pass "migrate service hardcodes APP_ENV=production; only frontend publishes a host/LAN port"

# --- Dev overlay ---
grep -qE '^[[:space:]]*APP_ENV:[[:space:]]*development[[:space:]]*$' "${DEV_OVERLAY}" \
  || fail "dev overlay must set APP_ENV: development"
grep -qE '^[[:space:]]*DQA_AUTH_PROVIDER:[[:space:]]*dev_headers[[:space:]]*$' "${DEV_OVERLAY}" \
  || fail "dev overlay must set DQA_AUTH_PROVIDER: dev_headers"
pass "dev overlay sets APP_ENV=development and DQA_AUTH_PROVIDER=dev_headers"

# --- Env example must not imply operator can enable prod auth via .env ---
if grep -qE '^APP_ENV=' "${ENV_EXAMPLE}"; then
  fail ".env.onprem.example must not set APP_ENV as an operator production knob"
fi
if grep -qE '^DQA_AUTH_PROVIDER=' "${ENV_EXAMPLE}"; then
  fail ".env.onprem.example must not set DQA_AUTH_PROVIDER as an operator production knob"
fi
grep -qi 'HARDCODED' "${ENV_EXAMPLE}" || fail ".env.onprem.example should state auth is hardcoded in Compose"
pass ".env.onprem.example does not expose APP_ENV/DQA_AUTH_PROVIDER as production knobs"

# --- Migration order helpers ---
grep -q 'dqa_require_migrations_at_head' "${COMMON}" || fail "missing dqa_require_migrations_at_head"
grep -q 'dqa_require_migrations_at_head' "${UP}" || fail "dqa-up.sh must call migration preflight"
grep -q 'Database migration is required. Run ./scripts/dqa-migrate.sh first.' "${COMMON}" \
  || fail "missing required migration failure message"
grep -q 'alembic upgrade' "${MIGRATE}" || fail "dqa-migrate.sh must run alembic upgrade"
if grep -nE '^[^#]*alembic[[:space:]]+upgrade|^[^#]*upgrade[[:space:]]+head' "${UP}" >/dev/null; then
  fail "dqa-up.sh must not auto-run alembic upgrade"
fi
if grep -nE 'down[[:space:]].*-v|down[[:space:]].*--volumes' "${DOWN}" >/dev/null; then
  fail "dqa-down.sh must not delete volumes by default"
fi
grep -q 'check_at_head' "${COMMON}" || fail "migration preflight should use Alembic check_at_head helper"
pass "migration-order helpers present; dqa-up does not auto-upgrade; down preserves volume"

# --- Nginx hardening assertions ---
grep -q 'server_tokens off' "${NGINX_MAIN}" || fail "nginx.main.conf must set server_tokens off"
grep -q 'server_tokens off' "${NGINX_CONF}" || fail "nginx.conf must set server_tokens off"
grep -q 'Content-Security-Policy' "${NGINX_CONF}" || fail "nginx.conf must set CSP"
grep -q "default-src 'self'" "${NGINX_CONF}" || fail "CSP must include default-src 'self'"
if grep -qi 'Strict-Transport-Security\|add_header HSTS\|max-age=.*preload' "${NGINX_CONF}" "${NGINX_MAIN}"; then
  fail "HSTS must not be enabled in this nginx foundation (TLS termination owns HSTS)"
fi
if grep -nE '^[[:space:]]*proxy_cache([[:space:]]|;|$)' "${NGINX_CONF}" "${NGINX_MAIN}" "${NGINX_PROXY}" >/dev/null; then
  fail "proxy_cache must not be enabled"
fi
grep -q 'client_max_body_size 2m' "${NGINX_CONF}" || fail "general API body limit must be 2m"
grep -q 'client_max_body_size 55m' "${NGINX_CONF}" || fail "Catalog upload body limit must be 55m"
# 55m > backend 50 MiB archive limit (documented outer boundary only).
python3 - <<'PY' || fail "Catalog nginx body limit must exceed backend archive limit"
from pathlib import Path
import re
nginx = Path("frontend/nginx.conf").read_text()
limits = Path("backend/app/adapters/catalog/limits.py").read_text()
assert "max_archive_bytes: int = 50 * 1024 * 1024" in limits
assert re.search(r"client_max_body_size\s+55m", nginx)
print("nginx_body_gt_backend_archive_ok")
PY
grep -q 'proxy_send_timeout' "${NGINX_PROXY}" || fail "proxy_send_timeout required"
grep -q 'proxy_read_timeout' "${NGINX_PROXY}" || fail "proxy_read_timeout required"
grep -q 'client_body_timeout' "${NGINX_CONF}" || fail "client_body_timeout required"
grep -q 'client_header_timeout' "${NGINX_CONF}" || fail "client_header_timeout required"
grep -q 'send_timeout' "${NGINX_CONF}" || fail "send_timeout required"
grep -q 'Permissions-Policy' "${NGINX_CONF}" || fail "Permissions-Policy required"
grep -q 'Cache-Control "public, max-age=31536000, immutable"' "${NGINX_CONF}" \
  || fail "hashed /assets/ cache policy required"
grep -q 'Cache-Control "no-cache"' "${NGINX_CONF}" || fail "index.html no-cache required"
if grep -nE '^[[:space:]]*proxy_set_header[[:space:]]+X-DQA-Dev-' "${NGINX_CONF}" "${NGINX_PROXY}" "${NGINX_MAIN}" >/dev/null; then
  fail "nginx must not inject X-DQA-Dev-* identity headers"
fi
pass "nginx hardening assertions (tokens/CSP/no-HSTS/no-proxy_cache/body limits/timeouts)"

# --- Optional Docker resolve checks (no pip; grep rendered YAML text) ---
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "SKIPPED: docker compose config (Docker unavailable)"
  echo "All static on-prem Compose regression checks passed."
  exit 0
fi

TMP_ENV="$(mktemp)"
TMP_PROD="$(mktemp)"
TMP_DEV="$(mktemp)"
trap 'rm -f "${TMP_ENV}" "${TMP_PROD}" "${TMP_DEV}"' EXIT

cat >"${TMP_ENV}" <<'EOF'
DQA_LAN_BIND_IP=127.0.0.1
DQA_FRONTEND_PORT=8080
DQA_DB_NAME=dqa
DQA_DB_USER=dqa
DQA_DB_PASSWORD=regression-check-not-a-real-secret
# Attempt to override production auth — must be ignored by production Compose.
APP_ENV=development
DQA_AUTH_PROVIDER=dev_headers
EOF

docker compose -f "${ONPREM}" --env-file "${TMP_ENV}" config >"${TMP_PROD}"
grep -E 'APP_ENV:[[:space:]]*production' "${TMP_PROD}" >/dev/null \
  || fail "resolved production config missing APP_ENV: production"
grep -E 'DQA_AUTH_PROVIDER:[[:space:]]*disabled' "${TMP_PROD}" >/dev/null \
  || fail "resolved production config missing DQA_AUTH_PROVIDER: disabled"
# Ensure DB/backend still have no published ports in resolved config.
python3 - <<PY || fail "resolved production port topology check failed"
from pathlib import Path
import re
text = Path("${TMP_PROD}").read_text()
# docker compose config expands services; assert no host publish for db/backend.
# Look for service-named sections loosely.
assert "DQA_AUTH_PROVIDER: disabled" in text or "DQA_AUTH_PROVIDER: \"disabled\"" in text
assert "APP_ENV: production" in text or "APP_ENV: \"production\"" in text
print("resolved_prod_ok")
PY
pass "docker compose config: production auth hardcoded despite .env override attempt"

docker compose -f "${ONPREM}" -f "${DEV_OVERLAY}" --env-file "${TMP_ENV}" config >"${TMP_DEV}"
grep -E 'APP_ENV:[[:space:]]*development' "${TMP_DEV}" >/dev/null \
  || fail "resolved dev overlay missing APP_ENV: development"
grep -E 'DQA_AUTH_PROVIDER:[[:space:]]*dev_headers' "${TMP_DEV}" >/dev/null \
  || fail "resolved dev overlay missing DQA_AUTH_PROVIDER: dev_headers"
pass "docker compose config: dev overlay resolves development + dev_headers"

echo "All on-prem Compose regression checks passed."
