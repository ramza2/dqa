#!/usr/bin/env bash
# S-03-E: disposable volume-backed PostgreSQL restart/durability acceptance.
# Strictly NEVER run against DQA's existing app/dev/on-prem PostgreSQL.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="dqa-s03e-disposable"
COMPOSE="${ROOT}/compose.s03e.disposable-pg.yaml"
VOLUME="${PROJECT}_s03e_pgdata"
PYTHON="${DQA_S03E_PYTHON:-${HOME}/dqa/.venv/bin/python}"

die() { echo "S03E_REFUSED: $*" >&2; exit 2; }
command -v docker >/dev/null 2>&1 || die "docker is not installed"
[[ -z "${DOCKER_HOST:-}" ]] || die "remote/custom DOCKER_HOST is forbidden"
docker_endpoint="$(docker context inspect --format '{{(index .Endpoints "docker").Host}}')"
[[ "${docker_endpoint}" == unix://* ]] || die "non-local Docker context forbidden"
[[ -f "${COMPOSE}" && -x "${PYTHON}" ]] || die "missing Compose or Python venv"
cd "${ROOT}"

dc() { docker compose --project-name "${PROJECT}" -f "${COMPOSE}" "$@"; }

# Fail closed before doing anything if the project or exact data volume exists.
existing="$(docker ps -aq --filter "label=com.docker.compose.project=${PROJECT}")"
[[ -z "${existing}" ]] || die "project already exists; never adopt another container"
if docker volume inspect "${VOLUME}" >/dev/null 2>&1; then
  die "disposable data volume already exists; never adopt or overwrite it"
fi

# Fixed, nonproduction, loopback-only connection settings.
export APP_ENV=test
export DQA_AUTH_PROVIDER=dev_headers
export DQA_DB_HOST=127.0.0.1
export DQA_DB_PORT=55440
export DQA_DB_NAME=dqa_s03e_disposable
export DQA_DB_USER=dqa_s03e_user
export DQA_DB_PASSWORD=dqa_s03e_test_only
export DQA_S03E_ISOLATED_PG=1
export DQA_SCHEMA_INSPECTOR_ENABLED=false
export DQA_SCHEMA_SNAPSHOT_REVIEW_ENABLED=false
export LLM_BASE_URL=""
export LLM_API_KEY=""
export EMBEDDING_BASE_URL=""
export EMBEDDING_API_KEY=""

started=0
cleanup() {
  local failure=0 volume_owner
  dc down --remove-orphans >/dev/null || failure=1
  if docker volume inspect "${VOLUME}" >/dev/null 2>&1; then
    volume_owner="$(docker volume inspect \
      --format '{{index .Labels "com.docker.compose.project"}}' "${VOLUME}")"
    if [[ "${volume_owner}" != "${PROJECT}" ]]; then
      echo "S03E_CLEANUP_REFUSED: volume ownership mismatch; manual inspection needed" >&2
      failure=1
    elif ! docker volume rm "${VOLUME}" >/dev/null; then
      echo "S03E_CLEANUP_FAILED: dedicated volume still present" >&2
      failure=1
    fi
  fi
  if [[ "${failure}" -ne 0 ]]; then
    return 1
  fi
  started=0
}
on_exit() {
  local result=$?
  trap - EXIT
  if [[ "${started}" == 1 ]]; then
    cleanup || result=1
  fi
  exit "${result}"
}
trap on_exit EXIT

started=1
dc up -d --wait --wait-timeout 90 disposable-pg

owner="$(docker volume inspect \
  --format '{{index .Labels "com.docker.compose.project"}}' "${VOLUME}")"
[[ "${owner}" == "${PROJECT}" ]] || die "volume is not from isolated Compose project"

cd "${ROOT}/backend"
# DB identity and emptiness must be checked BEFORE any Alembic operation.
"${PYTHON}" - <<'PY'
from sqlalchemy import create_engine, text
from app.core.config import get_settings

s = get_settings()
if not (
    s.app_env == "test"
    and (s.dqa_db_host, s.dqa_db_port, s.dqa_db_name, s.dqa_db_user)
    == ("127.0.0.1", 55440, "dqa_s03e_disposable", "dqa_s03e_user")
):
    raise SystemExit("S03E_REFUSED: unsafe migration target")
engine = create_engine(
    s.sqlalchemy_database_url,
    connect_args={"connect_timeout": 3, "options": "-c statement_timeout=10000"},
)
try:
    with engine.connect() as db:
        assert db.scalar(text("SELECT current_database()")) == "dqa_s03e_disposable"
        assert db.scalar(text("SELECT current_user")) == "dqa_s03e_user"
        assert db.scalar(text(
            "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname='public'"
        )) == 0, "nonempty database: refusing migration"
finally:
    engine.dispose()
PY

"${PYTHON}" -m alembic -c alembic.ini upgrade head

# Pre- and post-restart tests are entirely separate pytest/Python processes.
"${PYTHON}" -m pytest -q -rs \
  tests/test_s03e_disposable_pg_restart.py::test_before_restart_commit_snapshot_ready_warning_and_rollback_other
echo "S03E_BEFORE_RESTART_PASS"

pg_started() {
  "${PYTHON}" - <<'PY'
from sqlalchemy import create_engine, text
from app.core.config import get_settings

s = get_settings()
e = create_engine(s.sqlalchemy_database_url, connect_args={"connect_timeout": 3})
try:
    with e.connect() as db:
        print(db.scalar(text("SELECT pg_postmaster_start_time()")).isoformat())
finally:
    e.dispose()
PY
}

initial_started="$(pg_started)"
cd "${ROOT}"
# Restart only this dedicated PostgreSQL container; its named volume survives.
dc restart disposable-pg
dc up -d --wait --wait-timeout 90 disposable-pg
cd "${ROOT}/backend"
restarted_at="$(pg_started)"
[[ "${initial_started}" != "${restarted_at}" ]] || die "PostgreSQL restart not observed"

"${PYTHON}" -m pytest -q -rs \
  tests/test_s03e_disposable_pg_restart.py::test_after_restart_committed_rows_survive_retry_and_warning_stays_inactive
echo "S03E_AFTER_RESTART_PASS"

cd "${ROOT}"
cleanup
echo "DQA_S03E_DISPOSABLE_RESTART_PASS"
