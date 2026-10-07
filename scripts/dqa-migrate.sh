#!/usr/bin/env bash
# Run Alembic migrations against the on-prem DQA PostgreSQL.
#
# Authoritative production workflow:
#   1. ./scripts/dqa-migrate.sh   # starts DB only, then alembic upgrade head
#   2. ./scripts/dqa-up.sh        # refuses to start backend until DB is at head
#
# Alembic owns the full DQA application schema (head: 20261007_hist01).
# Backend startup never creates/alters tables; it only verifies Alembic head.
# This script does not start backend/frontend and never auto-runs on dqa-up.
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
