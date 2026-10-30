#!/usr/bin/env bash
# M5-S1A database-backed tests ONLY against an owned disposable PostgreSQL.
# tests/conftest.py forces localhost:5432/dqa and TRUNCATEs shared DQA tables.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${DQA_TEST_PYTHON:-${HOME}/dqa/.venv/bin/python}"
IMAGE="pgvector/pgvector:pg16"

die() { echo "M5S1A_ISOLATED_TEST_REFUSED: $*" >&2; exit 2; }

command -v docker >/dev/null 2>&1 || die "docker unavailable"
command -v ss >/dev/null 2>&1 || die "ss unavailable"
[[ -x "$PYTHON_BIN" ]] || die "test Python not executable"
[[ -z "${DOCKER_HOST:-}" ]] || die "custom Docker host forbidden"

DOCKER_ENDPOINT="$(docker context inspect --format '{{(index .Endpoints "docker").Host}}')" ||
  die "cannot inspect Docker context"
[[ "$DOCKER_ENDPOINT" == unix://* ]] || die "nonlocal Docker context forbidden"
docker info >/dev/null 2>&1 || die "Docker daemon unavailable"

[[ -z "$(ss -H -ltn '( sport = :5432 )')" ]] ||
  die "port 5432 is in use; NEVER touch a shared or existing PostgreSQL"
docker image inspect "$IMAGE" >/dev/null 2>&1 ||
  die "local image $IMAGE unavailable (no automatic pull)"

NAME="dqa-m5s1a-test-$$-$RANDOM"
if docker container inspect "$NAME" >/dev/null 2>&1; then
  die "disposable container name collision"
fi

STARTED=0
cleanup() {
  if [[ "$STARTED" == 1 ]]; then
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    echo "M5S1A_EPHEMERAL_POSTGRES_REMOVED"
  fi
}
trap cleanup EXIT

docker run --rm -d --pull=never \
  --name "$NAME" \
  --label openlink.dqa.purpose=m5s1a-ephemeral-test \
  --publish 127.0.0.1:5432:5432 \
  --tmpfs /var/lib/postgresql/data:rw,size=1g \
  -e POSTGRES_DB=dqa \
  -e POSTGRES_USER=dqa \
  -e POSTGRES_PASSWORD=dqa \
  "$IMAGE" >/dev/null
STARTED=1

READY=0
for _ in $(seq 1 45); do
  if docker exec "$NAME" pg_isready -q -h 127.0.0.1 -p 5432 -U dqa -d dqa; then
    READY=1
    break
  fi
  sleep 1
done
[[ "$READY" == 1 ]] || die "ephemeral PostgreSQL not ready"

# Confirm this process owns exactly the loopback binding tested by the suite.
BINDINGS="$(docker inspect -f '{{range .NetworkSettings.Ports}}{{range .}}{{.HostIp}}:{{.HostPort}}{{end}}{{end}}' "$NAME")"
[[ "$BINDINGS" == "127.0.0.1:5432" ]] ||
  die "unexpected Docker port binding: refusing to execute test suite"

export APP_ENV=test
export DQA_AUTH_PROVIDER=dev_headers
cd "$ROOT/backend"
"$PYTHON_BIN" -m pytest -q --tb=short \
  tests/test_m5_service_client_drafts.py \
  tests/test_m5_integration_status.py \
  tests/test_connection_profiles.py

echo "M5S1A_ISOLATED_BACKEND_TESTS_PASS"
