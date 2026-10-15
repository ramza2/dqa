#!/usr/bin/env bash
# S-03-F: isolated PostgreSQL SIGKILL + WAL crash recovery acceptance.
# NEVER run against a live DQA DB, Oracle/DEMIS or a production Docker host.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="dqa-s03f-disposable"
COMPOSE="${ROOT}/compose.s03f.disposable-pg.yaml"
VOLUME="${PROJECT}_s03f_pgdata"
PYTHON="${DQA_S03F_PYTHON:-${HOME}/dqa/.venv/bin/python}"
RUN_DIR=""
WRITER_PID=""
STARTED=0

die() { echo "S03F_REFUSED: $*" >&2; exit 2; }

command -v docker >/dev/null 2>&1 || die "docker unavailable"
[[ -z "${DOCKER_HOST:-}" ]] || die "custom DOCKER_HOST forbidden"
docker_endpoint="$(docker context inspect --format '{{(index .Endpoints "docker").Host}}')"
[[ "${docker_endpoint}" == unix://* ]] || die "nonlocal Docker context forbidden"
[[ -f "${COMPOSE}" && -x "${PYTHON}" ]] || die "missing Compose or DQA Python venv"

cd "${ROOT}"
dc() { docker compose --project-name "${PROJECT}" -f "${COMPOSE}" "$@"; }
[[ -z "$(docker ps -aq --filter "label=com.docker.compose.project=${PROJECT}")" ]] ||
  die "existing S-03-F Compose project: will not adopt or delete it"
if docker volume inspect "${VOLUME}" >/dev/null 2>&1; then
  die "existing S-03-F data volume: will not adopt or delete it"
fi

# Fixed local-test credentials and endpoint: never inherit DQA's live DB.
export APP_ENV=test
export DQA_AUTH_PROVIDER=dev_headers
export DQA_DB_HOST=127.0.0.1
export DQA_DB_PORT=55441
export DQA_DB_NAME=dqa_s03f_disposable
export DQA_DB_USER=dqa_s03f_user
export DQA_DB_PASSWORD=dqa_s03f_test_only
export DQA_S03F_ISOLATED_PG=1
export DQA_SCHEMA_INSPECTOR_ENABLED=false
export DQA_SCHEMA_SNAPSHOT_REVIEW_ENABLED=false
export LLM_BASE_URL=""
export LLM_API_KEY=""
export EMBEDDING_BASE_URL=""
export EMBEDDING_API_KEY=""

cleanup() {
  local failed=0 owner
  if [[ -n "${WRITER_PID}" ]]; then
    kill "${WRITER_PID}" 2>/dev/null || true
    wait "${WRITER_PID}" 2>/dev/null || true
    WRITER_PID=""
  fi
  dc down --remove-orphans >/dev/null || failed=1
  if docker volume inspect "${VOLUME}" >/dev/null 2>&1; then
    owner="$(docker volume inspect \
      --format '{{index .Labels "com.docker.compose.project"}}' "${VOLUME}")"
    if [[ "${owner}" != "${PROJECT}" ]]; then
      echo "S03F_CLEANUP_REFUSED: unexpected volume ownership; inspect manually" >&2
      failed=1
    elif ! docker volume rm "${VOLUME}" >/dev/null; then
      echo "S03F_CLEANUP_FAILED: disposable volume still exists" >&2
      failed=1
    fi
  fi
  if [[ -n "${RUN_DIR}" ]]; then
    rm -f "${RUN_DIR}/writer-flushed" "${RUN_DIR}/writer.log" || failed=1
    rmdir "${RUN_DIR}" || failed=1
    RUN_DIR=""
  fi
  [[ "${failed}" -eq 0 ]] || return 1
  STARTED=0
}
on_exit() {
  local result=$?
  trap - EXIT
  if [[ "${STARTED}" == 1 ]]; then
    cleanup || result=1
  fi
  exit "${result}"
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

STARTED=1
dc up -d --wait --wait-timeout 90 disposable-pg
owner="$(docker volume inspect \
  --format '{{index .Labels "com.docker.compose.project"}}' "${VOLUME}")"
[[ "${owner}" == "${PROJECT}" ]] || die "volume not owned by disposable project"

cd "${ROOT}/backend"
# Before ANY migration, prove this is the fresh, empty, dedicated DB.
"${PYTHON}" - <<'PY'
from sqlalchemy import create_engine, text
from app.core.config import get_settings

s = get_settings()
if not (
    s.app_env == "test"
    and (s.dqa_db_host, s.dqa_db_port, s.dqa_db_name, s.dqa_db_user)
    == ("127.0.0.1", 55441, "dqa_s03f_disposable", "dqa_s03f_user")
):
    raise SystemExit("S03F_REFUSED: unsafe migration target")
engine = create_engine(
    s.sqlalchemy_database_url,
    connect_args={"connect_timeout": 3, "options": "-c statement_timeout=10000"},
)
try:
    with engine.connect() as db:
        assert db.scalar(text("SELECT current_database()")) == "dqa_s03f_disposable"
        assert db.scalar(text("SELECT current_user")) == "dqa_s03f_user"
        assert db.scalar(text(
            "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname='public'"
        )) == 0, "nonempty DB: refusing migration"
finally:
    engine.dispose()
PY

"${PYTHON}" -m alembic -c alembic.ini upgrade head

# A separate Python process commits durable baseline Snapshot/Catalog state.
"${PYTHON}" -m pytest -q -rs \
  tests/test_s03f_disposable_pg_crash.py::test_seed_committed_baseline_before_forced_shutdown
echo "S03F_BASELINE_COMMITTED_PASS"

# Read PostgreSQL physical cluster identity and process start time.
pg_identity() {
  "${PYTHON}" - <<'PY'
from sqlalchemy import create_engine, text
from app.core.config import get_settings

s = get_settings()
engine = create_engine(s.sqlalchemy_database_url, connect_args={"connect_timeout": 3})
try:
    with engine.connect() as db:
        system_id = db.scalar(text("SELECT system_identifier FROM pg_control_system()"))
        started = db.scalar(text("SELECT pg_postmaster_start_time()")).isoformat()
        print(f"{system_id} {started}")
finally:
    engine.dispose()
PY
}
read -r BEFORE_SYSTEM_ID BEFORE_STARTED <<< "$(pg_identity)"
[[ -n "${BEFORE_SYSTEM_ID}" && -n "${BEFORE_STARTED}" ]] ||
  die "unable to capture baseline PG identity"

RUN_DIR="$(mktemp -d /tmp/dqa-s03f.XXXXXXXX)"
"${PYTHON}" tests/test_s03f_disposable_pg_crash.py \
  hold-uncommitted "${RUN_DIR}/writer-flushed" >"${RUN_DIR}/writer.log" 2>&1 &
WRITER_PID=$!

# The writer MUST have flushed snapshot+import+pointer+event and still be alive
# when the database's own process is SIGKILLed (not a graceful restart).
for _ in $(seq 1 100); do
  if [[ -s "${RUN_DIR}/writer-flushed" ]]; then
    break
  fi
  if ! kill -0 "${WRITER_PID}" 2>/dev/null; then
    cat "${RUN_DIR}/writer.log" >&2
    die "writer exited without the uncommitted flush marker"
  fi
  sleep 0.2
done
[[ -s "${RUN_DIR}/writer-flushed" ]] ||
  { cat "${RUN_DIR}/writer.log" >&2; die "writer did not flush in time"; }
kill -0 "${WRITER_PID}" 2>/dev/null || die "writer exited before forced shutdown"
echo "S03F_UNCOMMITTED_FLUSHED"

# Use Compose's exact isolated service selector rather than an arbitrary
# container name, image, host process, or killall.
cd "${ROOT}"
container_id="$(dc ps -q disposable-pg)"
[[ -n "${container_id}" ]] || die "missing dedicated PostgreSQL container"
project_label="$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "${container_id}")"
service_label="$(docker inspect --format '{{index .Config.Labels "com.docker.compose.service"}}' "${container_id}")"
[[ "${project_label}" == "${PROJECT}" && "${service_label}" == disposable-pg ]] ||
  die "refusing SIGKILL on unexpected Docker service"

dc kill --signal SIGKILL disposable-pg
# The DB backend was SIGKILLed while holding a flushed uncommitted write
# transaction. Terminate only our own waiting writer process.
kill "${WRITER_PID}" 2>/dev/null || true
wait "${WRITER_PID}" 2>/dev/null || true
WRITER_PID=""

# Reuse the same volume. Postgres must recover its own WAL after SIGKILL.
dc up -d --wait --wait-timeout 90 disposable-pg
cd "${ROOT}/backend"
read -r AFTER_SYSTEM_ID AFTER_STARTED <<< "$(pg_identity)"
[[ "${AFTER_SYSTEM_ID}" == "${BEFORE_SYSTEM_ID}" ]] ||
  die "PG system_identifier changed; not the same persistent cluster"
[[ "${AFTER_STARTED}" != "${BEFORE_STARTED}" ]] ||
  die "PostgreSQL postmaster start time unchanged; crash/restart not observed"
echo "S03F_CRASH_RESTART_CONFIRMED"

"${PYTHON}" -m pytest -q -rs \
  tests/test_s03f_disposable_pg_crash.py::test_after_sigkill_wal_recovery_preserves_only_committed_state
echo "S03F_RECOVERY_ASSERTIONS_PASS"

cd "${ROOT}"
cleanup
echo "DQA_S03F_DISPOSABLE_WAL_RECOVERY_PASS"
