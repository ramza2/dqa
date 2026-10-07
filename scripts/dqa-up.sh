#!/usr/bin/env bash
# Validate Compose config, enforce migrate-before-backend, then start the stack.
# Does not delete volumes. Does not auto-prune.
# Does NOT run alembic upgrade — migration remains an explicit operator action.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=dqa-common.sh
source "${SCRIPT_DIR}/dqa-common.sh"

dqa_preflight

echo "Validating Compose configuration..."
dqa_compose config >/dev/null

# Schema lifecycle is Alembic-only: refuse to start until DB is at head.
# Backend startup also re-checks head read-only and never runs create_all.
dqa_ensure_db_healthy
dqa_require_migrations_at_head

echo "Building and starting services (remove-orphans)..."
dqa_compose up -d --build --remove-orphans

echo "Waiting for backend readiness..."
attempts=0
until dqa_compose exec -T backend \
  python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=4)" \
  >/dev/null 2>&1; do
  attempts=$((attempts + 1))
  if (( attempts >= 36 )); then
    echo "error: backend not ready within timeout" >&2
    dqa_compose ps >&2 || true
    exit 1
  fi
  sleep 5
done

echo "Waiting for frontend HTTP..."
attempts=0
until dqa_compose exec -T frontend wget -q --spider http://127.0.0.1/ >/dev/null 2>&1; do
  attempts=$((attempts + 1))
  if (( attempts >= 24 )); then
    echo "error: frontend not ready within timeout" >&2
    dqa_compose ps >&2 || true
    exit 1
  fi
  sleep 5
done

bind_ip="$(grep -E '^DQA_LAN_BIND_IP=' "${DQA_ENV_FILE}" | tail -n 1 | cut -d= -f2-)"
frontend_port="$(grep -E '^DQA_FRONTEND_PORT=' "${DQA_ENV_FILE}" | tail -n 1 | cut -d= -f2- || true)"
frontend_port="${frontend_port:-8080}"

echo "DQA on-prem stack is up."
echo "Frontend (LAN entry): http://${bind_ip}:${frontend_port}"
echo "Note: production Compose hardcodes APP_ENV=production + DQA_AUTH_PROVIDER=disabled (fail closed)."
echo "Development auth requires the explicit docker-compose.onprem.dev.yml overlay."
dqa_compose ps
