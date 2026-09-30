#!/usr/bin/env bash
# Run Alembic migrations against the on-prem DQA PostgreSQL.
#
# Preferred production workflow:
#   1. Ensure dqa-db is healthy (./scripts/dqa-up.sh starts it, or start db alone)
#   2. ./scripts/dqa-migrate.sh   # alembic upgrade head
#   3. start/restart backend
#
# Caveat: Alembic currently owns connection_profiles + query_audit_events only.
# Backend startup still runs create_all for historical catalog/template tables.
# Recommended order on a fresh database: migrate first, then start backend.
# Running create_all first, then alembic, can fail when managed tables already exist.
#
# Never runs destructive downgrade.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=dqa-common.sh
source "${SCRIPT_DIR}/dqa-common.sh"

dqa_preflight

echo "Validating Compose configuration..."
dqa_compose config >/dev/null

echo "Ensuring dqa-db is up..."
dqa_compose up -d dqa-db

echo "Waiting for dqa-db health..."
attempts=0
until dqa_compose exec -T dqa-db pg_isready -U "$(grep -E '^DQA_DB_USER=' "${DQA_ENV_FILE}" | tail -n 1 | cut -d= -f2- || echo dqa)" >/dev/null 2>&1; do
  attempts=$((attempts + 1))
  if (( attempts >= 36 )); then
    echo "error: dqa-db not healthy within timeout" >&2
    exit 1
  fi
  sleep 2
done

echo "Running alembic upgrade head (one-shot migrate profile)..."
dqa_compose --profile migrate run --rm --no-deps migrate

echo "Migration complete."
