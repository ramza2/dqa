#!/usr/bin/env bash
# Run Alembic migrations against the on-prem DQA PostgreSQL.
#
# Preferred production workflow:
#   1. ./scripts/dqa-migrate.sh   # starts DB only, then alembic upgrade head
#   2. ./scripts/dqa-up.sh        # refuses to start backend until DB is at head
#
# Caveat: Alembic currently owns connection_profiles + query_audit_events only.
# Backend startup still runs create_all for historical catalog/template tables.
# Recommended order on a fresh database: migrate first, then start backend.
# Running create_all first, then alembic, can fail when managed tables already exist.
#
# This script does not start backend/frontend.
# Never runs destructive downgrade.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=dqa-common.sh
source "${SCRIPT_DIR}/dqa-common.sh"

dqa_preflight

echo "Validating Compose configuration..."
dqa_compose config >/dev/null

dqa_ensure_db_healthy

echo "Running alembic upgrade head (one-shot migrate profile)..."
dqa_compose --profile migrate run --rm --no-deps migrate

echo "Migration complete."
