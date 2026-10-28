#!/usr/bin/env bash
# Execute DQA M3-A integration tests ONLY on a disposable PostgreSQL instance.
# tests/conftest.py hardcodes localhost:5432/dqa and TRUNCATEs existing tables.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${DQA_TEST_PYTHON:-${HOME}/dqa/.venv/bin/python}"
IMAGE="pgvector/pgvector:pg16"

for cmd in docker ss npm git; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "M3A_TEST_REFUSED: missing $cmd" >&2
    exit 1
  fi
done
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "M3A_TEST_REFUSED: missing test Python interpreter" >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "M3A_TEST_REFUSED: Docker daemon unavailable" >&2
  exit 1
fi
if [[ -n "$(ss -H -ltn '( sport = :5432 )')" ]]; then
  echo "M3A_TEST_REFUSED: port 5432 is in use; never run against an existing DB" >&2
  exit 1
fi
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "M3A_TEST_REFUSED: local image $IMAGE missing" >&2
  echo "Download the image separately only if permitted." >&2
  exit 1
fi

NAME="dqa-m3a-test-$$-$RANDOM"
if docker container inspect "$NAME" >/dev/null 2>&1; then
  echo "M3A_TEST_REFUSED: generated container name already used" >&2
  exit 1
fi
STARTED=0
cleanup() {
  if [[ "$STARTED" == "1" ]]; then
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    echo "M3A_EPHEMERAL_POSTGRES_REMOVED"
  fi
}
trap cleanup EXIT

echo "===== ISOLATED POSTGRES START ====="
docker run --rm -d --pull=never \
  --name "$NAME" \
  --label "openlink.dqa.purpose=m3a-ephemeral-test" \
  --publish 127.0.0.1:5432:5432 \
  --tmpfs /var/lib/postgresql/data:rw,size=1g \
  -e POSTGRES_DB=dqa \
  -e POSTGRES_USER=dqa \
  -e POSTGRES_PASSWORD=dqa \
  "$IMAGE" >/dev/null
STARTED=1

ready=0
for _ in $(seq 1 45); do
  if docker exec "$NAME" pg_isready -q -U dqa -d dqa; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" != "1" ]]; then
  echo "M3A_TEST_FAIL: ephemeral PostgreSQL not ready" >&2
  exit 1
fi
docker inspect -f '{{range .NetworkSettings.Ports}}{{range .}}{{.HostIp}}:{{.HostPort}}{{end}}{{end}}' "$NAME" \
  | grep -Fx '127.0.0.1:5432' >/dev/null
echo "M3A_ISOLATED_POSTGRES_READY"

cd "$ROOT/backend"
echo "===== BACKEND TEST ====="
"$PYTHON_BIN" -m pytest -q --tb=short -x \
  tests/test_m3a_manual_template_catalog.py \
  tests/test_execution_form.py \
  tests/test_template_recommendation.py

cd "$ROOT/frontend"
echo "===== FRONTEND DEPENDENCIES ====="
npm ci --no-audit --no-fund
echo "===== FRONTEND TEST ====="
npm run test -- --run src/test/QueryAssistant.test.tsx
echo "===== BUILD / LINT ====="
npm run build
npm run lint

cd "$ROOT"
echo "===== DIFF CHECK ====="
git diff --check 5bd5bcd HEAD
echo "===== M3A_REVIEW_PASS ====="
