#!/usr/bin/env bash
# M3-B review: integration fixtures hardcode localhost:5432 and TRUNCATE tables.
# Refuse existing services; run only on disposable pgvector PostgreSQL.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${DQA_TEST_PYTHON:-${HOME}/dqa/.venv/bin/python}"
IMAGE=pgvector/pgvector:pg16
for x in docker ss npm git; do command -v "$x" >/dev/null || { echo "M3B_REFUSED: missing $x"; exit 1; }; done
test -x "$PYTHON_BIN" || { echo "M3B_REFUSED: Python missing"; exit 1; }
docker info >/dev/null 2>&1 || { echo "M3B_REFUSED: docker unavailable"; exit 1; }
if [[ -n "$(ss -H -ltn '( sport = :5432 )')" ]]; then
  echo "M3B_REFUSED: existing localhost PostgreSQL; NEVER reuse it for fixture TRUNCATE"
  exit 1
fi
docker image inspect "$IMAGE" >/dev/null 2>&1 || {
  echo "M3B_REFUSED: local pgvector/pgvector:pg16 image missing"
  exit 1
}
NAME="dqa-m3b-$-$RANDOM"
STARTED=0
cleanup() {
  if [[ "$STARTED" == "1" ]]; then
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    echo "M3B_EPHEMERAL_POSTGRES_REMOVED"
  fi
}
trap cleanup EXIT
docker run -d --rm --pull=never --name "$NAME" \
  --label "openlink.dqa.purpose=m3b-ephemeral" \
  -p 127.0.0.1:5432:5432 \
  --tmpfs /var/lib/postgresql/data:rw,size=1g \
  -e POSTGRES_DB=dqa -e POSTGRES_USER=dqa -e POSTGRES_PASSWORD=dqa \
  "$IMAGE" >/dev/null
STARTED=1
for i in $(seq 1 45); do
  if docker exec "$NAME" pg_isready -q -h 127.0.0.1 -p 5432 -U dqa -d dqa; then
    echo "M3B_EPHEMERAL_POSTGRES_READY"
    break
  fi
  if [[ "$i" == 45 ]]; then echo "M3B_REFUSED: PG not ready"; exit 1; fi
  sleep 1
done
docker inspect -f '{{range .NetworkSettings.Ports}}{{range .}}{{.HostIp}}:{{.HostPort}}{{end}}{{end}}' "$NAME" \
  | grep -Fx "127.0.0.1:5432" >/dev/null
cd "$ROOT/backend"
"$PYTHON_BIN" -m pytest -q --tb=short -x \
  tests/test_m3b_catalog_preview.py \
  tests/test_m3a_manual_template_catalog.py
cd "$ROOT/frontend"
npm ci --no-audit --no-fund
npm run test -- --run src/test/CatalogGraphicalBuilder.test.tsx src/test/QueryAssistant.test.tsx
npm run build
npm run lint
cd "$ROOT"
git diff --check 8adc41b HEAD
echo "M3B_REVIEW_PASS"
