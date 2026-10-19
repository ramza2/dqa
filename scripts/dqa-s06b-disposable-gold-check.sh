#!/usr/bin/env bash
# S-06-B/F/H using S-06-A disposable loopback PostgreSQL acceptance.
# NEVER use an existing DQA database. Own Compose project and tmpfs storage.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="dqa-s06a-disposable"
COMPOSE="${ROOT}/compose.s06a.disposable-pg.yaml"
PYTHON="${DQA_S06B_PYTHON:-${HOME}/dqa/.venv/bin/python}"

die() { echo "S06B_REFUSED: $*" >&2; exit 2; }

command -v docker >/dev/null 2>&1 || die "docker is not installed"
[[ -z "${DOCKER_HOST:-}" ]] || die "remote/custom DOCKER_HOST is forbidden"
docker_endpoint="$(docker context inspect --format '{{(index .Endpoints "docker").Host}}')"
[[ "${docker_endpoint}" == unix://* ]] || die "non-local Docker context forbidden"
[[ -f "${COMPOSE}" && -x "${PYTHON}" ]] || die "missing Compose or ${PYTHON}"
cd "${ROOT}"

dc() { docker compose --project-name "${PROJECT}" -f "${COMPOSE}" "$@"; }

# Never adopt or stop somebody else's previously existing project.
existing="$(docker ps -aq --filter "label=com.docker.compose.project=${PROJECT}")"
[[ -z "${existing}" ]] || die "disposable Compose project already exists; inspect manually"

# Fixed test-only values; do not inherit DQA server/production DB variables.
export APP_ENV="test"
export DQA_AUTH_PROVIDER="dev_headers"
export DQA_DB_HOST="127.0.0.1"
export DQA_DB_PORT="55442"
export DQA_DB_NAME="dqa_s06a_disposable"
export DQA_DB_USER="dqa_s06a_user"
export DQA_DB_PASSWORD="dqa_s06a_test_only"
export DQA_S06A_ISOLATED_PG="1"
export DQA_SCHEMA_INSPECTOR_ENABLED="false"
export DQA_SCHEMA_SNAPSHOT_REVIEW_ENABLED="false"
export LLM_BASE_URL=""
export LLM_API_KEY=""
export EMBEDDING_BASE_URL=""
export EMBEDDING_API_KEY=""

started=0
cleanup() {
  if [[ "${started}" == 1 ]]; then
    # Only our unique ephemeral Compose project; no --volumes, no shared DB.
    dc down --remove-orphans >/dev/null || true
  fi
}
trap cleanup EXIT

started=1
dc up -d --wait --wait-timeout 90 disposable-pg

cd "${ROOT}/backend"
# Refuse migrations unless the remote endpoint is precisely the *fresh* DB
# created by our isolated container, with no preexisting application tables.
"${PYTHON}" - <<'PY'
from sqlalchemy import create_engine, text
from app.core.config import get_settings

s = get_settings()
assert s.app_env == "test"
assert (s.dqa_db_host, s.dqa_db_port, s.dqa_db_name, s.dqa_db_user) == (
    "127.0.0.1", 55442, "dqa_s06a_disposable", "dqa_s06a_user"
), "unsafe DB target: refusing migrations"
engine = create_engine(
    s.sqlalchemy_database_url,
    connect_args={"connect_timeout": 3, "options": "-c statement_timeout=10000"},
)
try:
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT current_database()")) == "dqa_s06a_disposable"
        assert conn.scalar(text("SELECT current_user")) == "dqa_s06a_user"
        assert conn.scalar(text(
            "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname='public'"
        )) == 0, "database not empty: refusing migrations"
finally:
    engine.dispose()
PY

"${PYTHON}" -m alembic -c alembic.ini upgrade head
"${PYTHON}" -m pytest -q -rs -s \
  tests/test_s06b_relation_gold.py \
  tests/test_s06b_disposable_pg_gold_search.py \
  tests/test_s06f_disposable_warning_search_isolation.py \
  tests/test_s06h_disposable_25table_warning_index.py

# PASS only after this disposable Compose project is stopped/removed.
cleanup
started=0
echo "DQA_S06B_GOLD_PASS"
