#!/usr/bin/env bash
# Static regression checks for on-prem Compose auth + network boundaries.
# Does not require a running Docker daemon for source assertions.
# When Docker is available, also validates resolved `docker compose config` output.
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

python3 - <<'PY' || fail "migrate APP_ENV check failed"
from pathlib import Path
import re

text = Path("docker-compose.onprem.yml").read_text()
match = re.search(r"(?ms)^  migrate:\n(.*?)(?=^  [a-z].*:|\Z)", text)
assert match, "migrate service block not found"
block = match.group(1)
assert re.search(r"(?m)^\s+APP_ENV:\s*production\s*$", block), block
assert "APP_ENV: ${" not in block
print("migrate_app_env_ok")
PY
pass "migrate service hardcodes APP_ENV=production"

# --- Dev overlay ---
grep -qE '^[[:space:]]*APP_ENV:[[:space:]]*development[[:space:]]*$' "${DEV_OVERLAY}" \
  || fail "dev overlay must set APP_ENV: development"
grep -qE '^[[:space:]]*DQA_AUTH_PROVIDER:[[:space:]]*dev_headers[[:space:]]*$' "${DEV_OVERLAY}" \
  || fail "dev overlay must set DQA_AUTH_PROVIDER: dev_headers"
pass "dev overlay sets APP_ENV=development and DQA_AUTH_PROVIDER=dev_headers"

# --- Port publication topology ---
python3 - <<'PY' || fail "port topology check failed"
from pathlib import Path

try:
    import yaml
except ImportError:
    import subprocess
    import sys

    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml", "-q"])
    import yaml

onprem = yaml.safe_load(Path("docker-compose.onprem.yml").read_text())
db = onprem["services"]["dqa-db"]
backend = onprem["services"]["backend"]
frontend = onprem["services"]["frontend"]
assert "ports" not in db, "DB must not publish host ports"
assert "ports" not in backend, "backend must not publish host ports"
assert backend.get("expose") == ["8000"]
assert "ports" in frontend and frontend["ports"], "frontend must publish LAN port"
assert onprem["networks"]["data"].get("internal") is True
assert backend["environment"]["APP_ENV"] == "production"
assert backend["environment"]["DQA_AUTH_PROVIDER"] == "disabled"
assert onprem["services"]["migrate"]["environment"]["APP_ENV"] == "production"
print("topology_ok")
PY
pass "only frontend publishes a host/LAN port; DB and backend do not"

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
# Reject executable upgrade invocations; allow comments that say we do NOT upgrade.
if grep -nE '^[^#]*alembic[[:space:]]+upgrade|^[^#]*upgrade[[:space:]]+head' "${UP}" >/dev/null; then
  fail "dqa-up.sh must not auto-run alembic upgrade"
fi
if grep -nE 'down[[:space:]].*-v|down[[:space:]].*--volumes' "${DOWN}" >/dev/null; then
  fail "dqa-down.sh must not delete volumes by default"
fi
grep -q 'check_at_head' "${COMMON}" || fail "migration preflight should use Alembic check_at_head helper"
pass "migration-order helpers present; dqa-up does not auto-upgrade; down preserves volume"

# --- Optional Docker resolve checks ---
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
python3 - <<PY || fail "resolved production auth override check failed"
from pathlib import Path
import yaml

resolved = yaml.safe_load(Path("${TMP_PROD}").read_text())
backend = resolved["services"]["backend"]["environment"]
assert backend["APP_ENV"] == "production", backend
assert backend["DQA_AUTH_PROVIDER"] == "disabled", backend
assert resolved["services"]["migrate"]["environment"]["APP_ENV"] == "production"
assert "ports" not in resolved["services"]["dqa-db"]
assert "ports" not in resolved["services"]["backend"]
assert "ports" in resolved["services"]["frontend"]
print("resolved_prod_ok")
PY
pass "docker compose config: production auth hardcoded despite .env override attempt"

docker compose -f "${ONPREM}" -f "${DEV_OVERLAY}" --env-file "${TMP_ENV}" config >"${TMP_DEV}"
python3 - <<PY || fail "resolved dev overlay auth check failed"
from pathlib import Path
import yaml

resolved = yaml.safe_load(Path("${TMP_DEV}").read_text())
backend = resolved["services"]["backend"]["environment"]
assert backend["APP_ENV"] == "development", backend
assert backend["DQA_AUTH_PROVIDER"] == "dev_headers", backend
print("resolved_dev_ok")
PY
pass "docker compose config: dev overlay resolves development + dev_headers"

echo "All on-prem Compose regression checks passed."
