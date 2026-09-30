#!/usr/bin/env bash
# Shared helpers for DQA on-prem Compose scripts.
# shellcheck shell=bash

set -euo pipefail

DQA_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DQA_COMPOSE_FILE="${DQA_COMPOSE_FILE:-${DQA_ROOT}/docker-compose.onprem.yml}"
DQA_ENV_FILE="${DQA_ENV_FILE:-${DQA_ROOT}/.env.onprem}"
DQA_COMPOSE_PROJECT_NAME="${DQA_COMPOSE_PROJECT_NAME:-dqa-onprem}"

dqa_require_cmd() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "error: required command not found: ${cmd}" >&2
    exit 1
  fi
}

dqa_require_env_file() {
  if [[ ! -f "${DQA_ENV_FILE}" ]]; then
    echo "error: missing ${DQA_ENV_FILE}" >&2
    echo "Copy .env.onprem.example to .env.onprem and set required values (including DQA_DB_PASSWORD)." >&2
    exit 1
  fi
}

# Ensure a key exists with a non-empty value. Never print the value.
dqa_require_env_key() {
  local key="$1"
  local line
  line="$(grep -E "^${key}=" "${DQA_ENV_FILE}" | tail -n 1 || true)"
  if [[ -z "${line}" ]]; then
    echo "error: required variable ${key} is missing from ${DQA_ENV_FILE}" >&2
    exit 1
  fi
  local value="${line#*=}"
  # Strip optional surrounding quotes without echoing secrets elsewhere.
  if [[ "${value}" == \"*\" && "${value}" == *\" ]]; then
    value="${value:1:-1}"
  elif [[ "${value}" == \'*\' && "${value}" == *\' ]]; then
    value="${value:1:-1}"
  fi
  if [[ -z "${value}" ]]; then
    echo "error: required variable ${key} is empty in ${DQA_ENV_FILE}" >&2
    exit 1
  fi
}

dqa_compose() {
  docker compose \
    -p "${DQA_COMPOSE_PROJECT_NAME}" \
    -f "${DQA_COMPOSE_FILE}" \
    --env-file "${DQA_ENV_FILE}" \
    "$@"
}

dqa_preflight() {
  dqa_require_cmd docker
  if ! docker compose version >/dev/null 2>&1; then
    echo "error: docker compose is required" >&2
    exit 1
  fi
  dqa_require_env_file
  dqa_require_env_key DQA_DB_PASSWORD
  dqa_require_env_key DQA_LAN_BIND_IP
}

dqa_db_user() {
  local line value
  line="$(grep -E '^DQA_DB_USER=' "${DQA_ENV_FILE}" | tail -n 1 || true)"
  value="${line#*=}"
  if [[ -z "${value}" ]]; then
    echo "dqa"
  else
    echo "${value}"
  fi
}

# Start dqa-db only and wait until healthy. Does not start backend/frontend.
dqa_ensure_db_healthy() {
  echo "Ensuring dqa-db is up..."
  dqa_compose up -d dqa-db

  echo "Waiting for dqa-db health..."
  local attempts=0
  local db_user
  db_user="$(dqa_db_user)"
  until dqa_compose exec -T dqa-db pg_isready -U "${db_user}" >/dev/null 2>&1; do
    attempts=$((attempts + 1))
    if (( attempts >= 36 )); then
      echo "error: dqa-db not healthy within timeout" >&2
      exit 1
    fi
    sleep 2
  done
}

# Non-destructive Alembic head check. Never auto-upgrades.
# Fail closed when alembic_version is absent or not equal to every script head.
dqa_require_migrations_at_head() {
  echo "Checking Alembic migration state (non-destructive)..."
  # Ensure the migrate/backend image exists so the check can run Alembic APIs.
  dqa_compose build migrate >/dev/null

  if ! dqa_compose --profile migrate run --rm --no-deps migrate \
    python alembic/check_at_head.py; then
    echo "Database migration is required. Run ./scripts/dqa-migrate.sh first." >&2
    exit 1
  fi
}

dqa_env_value() {
  local key="$1"
  local default_value="${2:-}"
  local line value
  line="$(grep -E "^${key}=" "${DQA_ENV_FILE}" | tail -n 1 || true)"
  if [[ -z "${line}" ]]; then
    echo "${default_value}"
    return 0
  fi
  value="${line#*=}"
  if [[ "${value}" == \"*\" && "${value}" == *\" ]]; then
    value="${value:1:-1}"
  elif [[ "${value}" == \'*\' && "${value}" == *\' ]]; then
    value="${value:1:-1}"
  fi
  if [[ -z "${value}" ]]; then
    echo "${default_value}"
  else
    echo "${value}"
  fi
}

dqa_db_name() {
  dqa_env_value DQA_DB_NAME dqa
}

# Backup directory: DQA_BACKUP_DIR env, else .env.onprem, else ./backups
dqa_backup_dir() {
  if [[ -n "${DQA_BACKUP_DIR:-}" ]]; then
    echo "${DQA_BACKUP_DIR}"
    return 0
  fi
  local from_env
  from_env="$(dqa_env_value DQA_BACKUP_DIR "")"
  if [[ -n "${from_env}" ]]; then
    echo "${from_env}"
  else
    echo "${DQA_ROOT}/backups"
  fi
}

dqa_service_is_running() {
  local service="$1"
  local running
  running="$(dqa_compose ps --status running --services 2>/dev/null || true)"
  printf '%s\n' "${running}" | grep -qx "${service}"
}

# Refuse when application containers that hold DB sessions are up.
dqa_require_app_stopped_for_restore() {
  local blockers=()
  if dqa_service_is_running backend; then
    blockers+=("backend")
  fi
  if dqa_service_is_running frontend; then
    blockers+=("frontend")
  fi
  if dqa_service_is_running migrate; then
    blockers+=("migrate")
  fi
  if ((${#blockers[@]} > 0)); then
    echo "error: refuse restore while application services are running: ${blockers[*]}" >&2
    echo "Stop them first with: ./scripts/dqa-down.sh" >&2
    exit 1
  fi
}

# Run a command inside dqa-db without printing connection secrets.
dqa_db_exec() {
  dqa_compose exec -T dqa-db "$@"
}
