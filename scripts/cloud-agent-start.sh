#!/usr/bin/env bash
#
# Cloud Agent start phase for DEMIS Query Assistant (DQA).
#
# Per-boot reconciliation. Safe to run repeatedly.
# - starts the local PostgreSQL cluster
# - ensures the DQA role, database, and vector extension exist
# - applies Alembic migrations when the backend has them
# - starts the API and Vite dev servers when their dependencies are installed
#
# Does not install packages. Does not print secrets.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

log() { printf '\n[start] %s\n' "$*"; }

read_env() {
  local key="$1"
  local default="$2"
  local line=""
  if [[ -f "$ROOT_DIR/.env" ]]; then
    line="$(grep -E "^${key}=" "$ROOT_DIR/.env" | tail -n 1 || true)"
  fi
  if [[ -z "$line" ]]; then
    printf '%s' "$default"
    return
  fi
  local value="${line#*=}"
  value="${value%\"}"
  value="${value#\"}"
  value="${value%\'}"
  value="${value#\'}"
  printf '%s' "$value"
}

require_ident() {
  local label="$1"
  local value="$2"
  if [[ ! "$value" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    log "Refusing unsafe ${label}."
    exit 1
  fi
}

sql_literal() {
  local value="$1"
  value="${value//\'/\'\'}"
  printf "'%s'" "$value"
}

DB_NAME="$(read_env DQA_DB_NAME dqa)"
DB_USER="$(read_env DQA_DB_USER dqa)"
DB_PASSWORD="$(read_env DQA_DB_PASSWORD dqa)"
AUTH_PROVIDER="$(read_env DQA_AUTH_PROVIDER disabled)"
require_ident "database name" "$DB_NAME"
require_ident "database user" "$DB_USER"

if ! command -v pg_lsclusters >/dev/null 2>&1; then
  log "PostgreSQL is not installed; run scripts/cloud-agent-install.sh first."
  exit 0
fi

read -r PG_VER PG_CLUSTER < <(pg_lsclusters -h | awk 'NR==1 {print $1, $2}')
PG_VER="${PG_VER:-16}"
PG_CLUSTER="${PG_CLUSTER:-main}"

status="$(pg_lsclusters -h | awk -v v="$PG_VER" -v c="$PG_CLUSTER" '$1==v && $2==c {print $4}')"
if [[ "$status" != "online" ]]; then
  log "Starting PostgreSQL cluster ${PG_VER}/${PG_CLUSTER}."
  sudo pg_ctlcluster "$PG_VER" "$PG_CLUSTER" start
else
  log "PostgreSQL cluster ${PG_VER}/${PG_CLUSTER} already online."
fi

for _ in $(seq 1 30); do
  if sudo -u postgres pg_isready -q; then
    break
  fi
  sleep 1
done
if ! sudo -u postgres pg_isready -q; then
  log "PostgreSQL did not accept connections."
  exit 1
fi

if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1; then
  log "Creating role '${DB_USER}'."
  sudo -u postgres psql -c "CREATE ROLE ${DB_USER} LOGIN PASSWORD $(sql_literal "$DB_PASSWORD");"
else
  log "Role '${DB_USER}' already exists; syncing local password."
  sudo -u postgres psql -c "ALTER ROLE ${DB_USER} LOGIN PASSWORD $(sql_literal "$DB_PASSWORD");"
fi

if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1; then
  log "Creating database '${DB_NAME}' owned by '${DB_USER}'."
  sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"
else
  log "Database '${DB_NAME}' already exists."
fi

if sudo -u postgres psql -d "$DB_NAME" -tAc "SELECT 1 FROM pg_available_extensions WHERE name='vector'" | grep -q 1; then
  log "Ensuring vector extension on '${DB_NAME}'."
  sudo -u postgres psql -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector;"
else
  log "pgvector is not installed; skipping vector extension."
fi

if [[ -x "$ROOT_DIR/backend/.venv/bin/alembic" && -f "$ROOT_DIR/backend/alembic.ini" ]]; then
  log "Applying Alembic migrations."
  (
    cd "$ROOT_DIR/backend"
    .venv/bin/alembic upgrade head
  )
else
  log "No Alembic environment in backend/.venv; skipping migrations."
fi

wait_for_http() {
  local url="$1"
  local attempts="$2"
  local i
  for i in $(seq 1 "$attempts"); do
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

start_backend() {
  local uvicorn="$ROOT_DIR/backend/.venv/bin/uvicorn"
  if [[ ! -x "$uvicorn" ]]; then
    log "Backend virtualenv not present; skipping API server."
    return 0
  fi
  if wait_for_http "http://127.0.0.1:8000/health" 1; then
    log "Backend already responding on 127.0.0.1:8000."
    return 0
  fi
  if tmux has-session -t dqa-backend 2>/dev/null; then
    tmux kill-session -t dqa-backend
  fi
  log "Starting backend on 127.0.0.1:8000."
  tmux new-session -d -s dqa-backend -c "$ROOT_DIR/backend" \
    "exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
  if ! wait_for_http "http://127.0.0.1:8000/health" 60; then
    log "Backend did not become healthy."
    tmux capture-pane -pt dqa-backend -S -80 >&2 || true
    exit 1
  fi
  if ! wait_for_http "http://127.0.0.1:8000/health/ready" 30; then
    log "Backend liveness passed but readiness failed."
    tmux capture-pane -pt dqa-backend -S -80 >&2 || true
    exit 1
  fi
  log "Backend is ready on 127.0.0.1:8000."
}

start_frontend() {
  if [[ ! -f "$ROOT_DIR/frontend/package.json" || ! -d "$ROOT_DIR/frontend/node_modules" ]]; then
    log "Frontend dependencies not installed; skipping Vite."
    return 0
  fi
  if ! command -v npm >/dev/null 2>&1; then
    log "npm is not on PATH; skipping Vite."
    return 0
  fi
  if wait_for_http "http://127.0.0.1:5173/" 1; then
    log "Frontend already responding on 127.0.0.1:5173."
    return 0
  fi
  if tmux has-session -t dqa-frontend 2>/dev/null; then
    tmux kill-session -t dqa-frontend
  fi
  log "Starting Vite on 127.0.0.1:5173."
  local vite_identity=""
  if [[ "$AUTH_PROVIDER" == "dev_headers" ]]; then
    vite_identity="export VITE_DQA_DEV_ACTOR=query-operator VITE_DQA_DEV_ROLES=query_operator; "
  fi
  tmux new-session -d -s dqa-frontend -c "$ROOT_DIR/frontend" \
    "${vite_identity}exec npm run dev -- --host 127.0.0.1 --port 5173 --strictPort"
  if ! wait_for_http "http://127.0.0.1:5173/" 60; then
    log "Vite did not become ready."
    tmux capture-pane -pt dqa-frontend -S -80 >&2 || true
    exit 1
  fi
  log "Frontend is ready on 127.0.0.1:5173."
}

start_backend
start_frontend

log "PostgreSQL ready on localhost:5432 (db=${DB_NAME}, user=${DB_USER})."
