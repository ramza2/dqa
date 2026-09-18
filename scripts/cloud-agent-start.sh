#!/usr/bin/env bash
#
# Cloud Agent start phase for DEMIS Query Assistant (DQA).
#
# Per-boot reconciliation: bring up the local development PostgreSQL cluster and
# make sure the DQA application role and database exist. Safe to run repeatedly.
#
# It intentionally does NOT install packages or build the project (that belongs
# in the install phase) and does NOT start application dev servers (there is no
# application code in the bootstrap phase yet).
set -euo pipefail

log() { printf '\n[start] %s\n' "$*"; }

DB_NAME="${DQA_DB_NAME:-dqa}"
DB_USER="${DQA_DB_USER:-dqa}"
DB_PASSWORD="${DQA_DB_PASSWORD:-dqa}"

if ! command -v pg_lsclusters >/dev/null 2>&1; then
  log "PostgreSQL is not installed; run scripts/cloud-agent-install.sh first."
  exit 0
fi

# Detect the installed cluster version/name (defaults to the first listed).
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

# Wait for the server to accept connections.
for _ in $(seq 1 30); do
  if sudo -u postgres pg_isready -q; then
    break
  fi
  sleep 1
done

# Ensure the application role exists (idempotent).
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1; then
  log "Creating role '${DB_USER}'."
  sudo -u postgres psql -c "CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASSWORD}';"
else
  log "Role '${DB_USER}' already exists."
fi

# Ensure the application database exists (idempotent).
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1; then
  log "Creating database '${DB_NAME}' owned by '${DB_USER}'."
  sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"
else
  log "Database '${DB_NAME}' already exists."
fi

log "PostgreSQL ready on localhost:5432 (db=${DB_NAME}, user=${DB_USER})."
