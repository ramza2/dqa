#!/usr/bin/env bash
# P30-C: disposable, loopback-only, tmpfs PostgreSQL + test-only Oracle adapter.
# DANGER: root conftest.db_session TRUNCATEs tables. Run ONLY here, after
# verifying a new Docker Compose project + identity marker; NEVER on DQA DB.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="dqa-p30c-disposable"
COMPOSE="${ROOT}/compose.p30c.disposable-pg.yaml"
PYTHON="${DQA_P30C_PYTHON:-${HOME}/dqa/.venv/bin/python}"

die() { echo "P30C_REFUSED: $*" >&2; exit 2; }
command -v docker >/dev/null 2>&1 || die "docker not installed"
[[ -z "${DOCKER_HOST:-}" ]] || die "custom DOCKER_HOST forbidden"
docker_endpoint="$(docker context inspect --format '{{(index .Endpoints "docker").Host}}')"
[[ "${docker_endpoint}" == unix://* ]] || die "remote Docker context forbidden"
[[ -f "${COMPOSE}" && -x "${PYTHON}" ]] || die "missing Compose file or verified test venv"

cd "${ROOT}"
dc() { docker compose --project-name "${PROJECT}" -f "${COMPOSE}" "$@"; }

# Never claim/adopt a pre-existing Compose project, even with matching name.
existing="$(docker ps -aq --filter "label=com.docker.compose.project=${PROJECT}")"
[[ -z "${existing}" ]] || die "project already exists, inspect manually"
# Refuse a pre-existing binding even if an unrelated service has it.
if command -v ss >/dev/null 2>&1; then
  ! ss -H -ltn '( sport = :55448 )' | grep -q . || die "loopback port 55448 already bound"
fi

# Explicit synthetic DB identity; never inherit existing server DQA_DB_*.
export APP_ENV="test"
export DQA_AUTH_PROVIDER="dev_headers"
export DQA_DB_HOST="127.0.0.1"
export DQA_DB_PORT="55448"
export DQA_DB_NAME="dqa_p30c_disposable"
export DQA_DB_USER="dqa_p30c_user"
export DQA_DB_PASSWORD="p30c_synthetic_only"
export DQA_P30C_ISOLATED_PG="p30c-v1"
export DQA_SCHEMA_INSPECTOR_ENABLED="false"
export DQA_SCHEMA_SNAPSHOT_REVIEW_ENABLED="false"
export DQA_MCP_ENABLED="true"
export DQA_MCP_QUERY_EXECUTION_ENABLED="true"
export LLM_BASE_URL=""
export LLM_API_KEY=""
export EMBEDDING_BASE_URL=""
export EMBEDDING_API_KEY=""

started=0
cleanup() {
  if [[ "${started}" == 1 ]]; then
    # Only an originally empty disposable project, tmpfs holds all DB bytes.
    dc down --remove-orphans >/dev/null || return 1
    started=0
  fi
}
trap 'cleanup || echo "P30C_CLEANUP_FAILED: manual inspection required" >&2' EXIT
started=1
dc up -d --wait --wait-timeout 90 disposable-pg

cid="$(dc ps -q disposable-pg)"
[[ -n "${cid}" ]] || die "disposable postgres container missing"
label="$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project" }}' "${cid}")"
[[ "${label}" == "${PROJECT}" ]] || die "compose project identity mismatch"
mapping="$(docker port "${cid}" 5432/tcp)"
[[ "${mapping}" == "127.0.0.1:55448" ]] || die "unexpected PostgreSQL published port: ${mapping}"

cd "${ROOT}/backend"
# Validate the empty container-owned database FIRST. Install a unique
# database COMMENT marker before Alembic and pytest fixtures may create or
# truncate tables. The nested conftest revalidates it on every test.
"${PYTHON}" - <<'PY'
from sqlalchemy import create_engine, text
from app.core.config import get_settings

s = get_settings()
if (s.app_env, s.dqa_db_host, s.dqa_db_port, s.dqa_db_name, s.dqa_db_user) != (
    "test", "127.0.0.1", 55448, "dqa_p30c_disposable", "dqa_p30c_user"
):
    raise SystemExit("P30C_REFUSED: unexpected DB settings")

engine = create_engine(
    s.sqlalchemy_database_url,
    connect_args={"connect_timeout": 3, "options": "-c statement_timeout=10000"},
)
try:
    with engine.begin() as conn:
        row = conn.execute(text("SELECT current_database(), current_user")).one()
        if tuple(row) != ("dqa_p30c_disposable", "dqa_p30c_user"):
            raise SystemExit("P30C_REFUSED: unexpected database or role")
        count = conn.scalar(text(
            "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname='public'"
        ))
        if count != 0:
            raise SystemExit("P30C_REFUSED: database is not empty")
        conn.execute(text(
            "COMMENT ON DATABASE dqa_p30c_disposable IS 'DQA_P30C_DISPOSABLE_DB_V1'"
        ))
finally:
    engine.dispose()
PY

"${PYTHON}" -m alembic -c alembic.ini upgrade head
"${PYTHON}" -m pytest -q -rs \
  tests/p30c/test_web_mcp_isolated_asgi.py

cleanup
trap - EXIT
echo "DQA_P30C_DISCOVERY_ASGI_PASS"
