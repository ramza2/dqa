#!/usr/bin/env bash
# M4-A isolated verification harness.
#
# 1) Refuse any non-disposable PostgreSQL (port 5432 must be free; never touch ops DB).
# 2) Start ephemeral pgvector/pg16 on 127.0.0.1:5432 (tmpfs PGDATA).
# 3) Run LLM-free API contract pytest (Fake adapter; no Oracle socket).
# 4) Optionally probe Oracle Mock TCP separately.
#    Labels: API_CONTRACT / ORACLE_MOCK_REACHABLE / LIVE_E2E=NOT_RUN
#    Never print M4A_REVIEW_PASS or LIVE_E2E=PASS from this harness.
#
# Existing dqa-oracle-mock-smoke.sh is left intact for the legacy LLM path.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${DQA_TEST_PYTHON:-${ROOT}/backend/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="${DQA_TEST_PYTHON:-${HOME}/dqa/backend/.venv/bin/python}"
fi
IMAGE="pgvector/pgvector:pg16"
# Fixed allowlisted mock identity (same as app.services.oracle_mock_actions).
ALLOWED_MOCK_HOST="demis-oracle-test"
ALLOWED_MOCK_PORT="1521"

port_in_use_5432() {
  if command -v ss >/dev/null 2>&1; then
    [[ -n "$(ss -H -ltn '( sport = :5432 )' 2>/dev/null || true)" ]]
    return $?
  fi
  "$PYTHON_BIN" - <<'PY'
import socket
s = socket.socket()
s.settimeout(0.5)
try:
    s.connect(("127.0.0.1", 5432))
except OSError:
    raise SystemExit(1)
else:
    s.close()
    raise SystemExit(0)
PY
}

validate_mock_endpoint() {
  local host="$1" port="$2"
  if [[ ! "$host" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
    echo "M4A_ORACLE_MOCK_BLOCKED: mock host failed safe-charset validation" >&2
    return 1
  fi
  if [[ ! "$port" =~ ^[0-9]+$ ]] || (( port < 1 || port > 65535 )); then
    echo "M4A_ORACLE_MOCK_BLOCKED: mock port failed numeric validation" >&2
    return 1
  fi
  if [[ "$host" != "$ALLOWED_MOCK_HOST" || "$port" != "$ALLOWED_MOCK_PORT" ]]; then
    echo "M4A_ORACLE_MOCK_BLOCKED: host/port is not the allowlisted Oracle Mock endpoint" >&2
    return 1
  fi
  return 0
}

for cmd in docker git; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "M4A_ISOLATED_HARNESS_BLOCKED: missing $cmd" >&2
    exit 2
  fi
done
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "M4A_ISOLATED_HARNESS_BLOCKED: missing test Python interpreter" >&2
  exit 2
fi
if ! docker info >/dev/null 2>&1; then
  echo "M4A_ISOLATED_HARNESS_BLOCKED: Docker daemon unavailable" >&2
  exit 2
fi
if port_in_use_5432; then
  echo "M4A_ISOLATED_HARNESS_BLOCKED: port 5432 is in use; refuse existing/shared DB" >&2
  exit 2
fi
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "M4A_ISOLATED_HARNESS_BLOCKED: local image $IMAGE missing" >&2
  exit 2
fi

NAME="dqa-m4a-test-$$-$RANDOM"
STARTED=0
cleanup() {
  if [[ "$STARTED" == "1" ]]; then
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    echo "M4A_EPHEMERAL_POSTGRES_REMOVED"
  fi
}
trap cleanup EXIT

echo "===== ISOLATED POSTGRES START ====="
docker run --rm -d --pull=never \
  --name "$NAME" \
  --label "openlink.dqa.purpose=m4a-ephemeral-test" \
  --publish 127.0.0.1:5432:5432 \
  --tmpfs /var/lib/postgresql/data:rw,size=1g \
  -e POSTGRES_DB=dqa \
  -e POSTGRES_USER=dqa \
  -e POSTGRES_PASSWORD=dqa \
  "$IMAGE" >/dev/null
STARTED=1

ready=0
for _ in $(seq 1 45); do
  if docker exec "$NAME" pg_isready -q -h 127.0.0.1 -p 5432 -U dqa -d dqa; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" != "1" ]]; then
  echo "M4A_TEST_FAIL: ephemeral PostgreSQL not ready" >&2
  exit 1
fi
echo "M4A_ISOLATED_POSTGRES_READY"

cd "$ROOT/backend"
echo "===== API CONTRACT (Fake adapter; no Oracle) ====="
"$PYTHON_BIN" -m pytest -q --tb=short \
  tests/test_m4a_llmfree_execution_contract.py \
  tests/test_m4a_script_safety.py
echo "M4A_API_CONTRACT_PASS"

echo "===== ORACLE MOCK TCP PROBE (not Live E2E) ====="
MOCK_HOST="${DQA_M4A_ORACLE_MOCK_HOST:-$ALLOWED_MOCK_HOST}"
MOCK_PORT="${DQA_M4A_ORACLE_MOCK_PORT:-$ALLOWED_MOCK_PORT}"
ORACLE_STATUS=blocked
if ! validate_mock_endpoint "$MOCK_HOST" "$MOCK_PORT"; then
  ORACLE_STATUS=blocked
elif [[ -z "${DEMIS_SECRET_ORACLE_PASSWORD:-}" ]]; then
  echo "M4A_ORACLE_MOCK_BLOCKED: DEMIS_SECRET_ORACLE_PASSWORD unset"
  ORACLE_STATUS=blocked
else
  export DQA_M4A_ORACLE_MOCK_HOST="$MOCK_HOST"
  export DQA_M4A_ORACLE_MOCK_PORT="$MOCK_PORT"
  if "$PYTHON_BIN" - <<'PY'
import os
import socket
import sys

host = os.environ["DQA_M4A_ORACLE_MOCK_HOST"]
port_raw = os.environ["DQA_M4A_ORACLE_MOCK_PORT"]
if host != "demis-oracle-test" or port_raw != "1521":
    print("not allowlisted", file=sys.stderr)
    raise SystemExit(1)
port = int(port_raw)
s = socket.socket()
s.settimeout(3)
try:
    s.connect((host, port))
except OSError as exc:
    print(exc.__class__.__name__, file=sys.stderr)
    raise SystemExit(1)
finally:
    s.close()
PY
  then
    echo "M4A_ORACLE_MOCK_REACHABLE: allowlisted endpoint TCP open"
    echo "NOTE: TCP reachable is NOT Live E2E PASS. Run scripts/dqa-m4a-llmfree-smoke.sh separately."
    ORACLE_STATUS=reachable
  else
    echo "M4A_ORACLE_MOCK_BLOCKED: allowlisted endpoint not reachable"
    ORACLE_STATUS=blocked
  fi
fi

cd "$ROOT"
echo "===== DIFF CHECK ====="
git diff --check 79210d1 HEAD

echo "===== M4A SUMMARY ====="
echo "API_CONTRACT=PASS"
if [[ "$ORACLE_STATUS" == "reachable" ]]; then
  echo "ORACLE_MOCK_REACHABLE=yes"
else
  echo "ORACLE_MOCK_REACHABLE=no"
  echo "ORACLE_MOCK=BLOCKED"
fi
echo "LIVE_E2E=NOT_RUN"
echo "M4A_ISOLATED_HARNESS_COMPLETE"
# Never emit M4A_REVIEW_PASS or LIVE_E2E=PASS from this harness.
exit 0
