#!/usr/bin/env bash
# Restore DQA PostgreSQL from a pg_dump custom-format archive.
#
# Deliberately destructive. Fail closed.
#
# Usage:
#   ./scripts/dqa-restore.sh /path/to/dqa_UTC.dump RESTORE
#
# Safeguards:
# - explicit RESTORE confirmation token (not interactive yes/no)
# - SHA-256 sidecar required and verified
# - pg_restore --list archive validation
# - refuse while backend/frontend/migrate are running
# - no docker compose down -v
# - does not auto-start application services
# - does not restore arbitrary SQL text via psql
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=dqa-common.sh
source "${SCRIPT_DIR}/dqa-common.sh"

usage() {
  echo "Usage: $0 <path-to-dqa_*.dump> RESTORE" >&2
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -ne 2 ]]; then
  usage
  echo "error: dump path and explicit confirmation token RESTORE are required" >&2
  exit 1
fi

dump_path="$1"
confirm_token="$2"

if [[ "${confirm_token}" != "RESTORE" ]]; then
  echo "error: refusing restore without explicit confirmation token RESTORE" >&2
  exit 1
fi

if [[ ! -f "${dump_path}" ]]; then
  echo "error: backup archive not found" >&2
  exit 1
fi

checksum_path="${dump_path}.sha256"
if [[ ! -f "${checksum_path}" ]]; then
  echo "error: missing SHA-256 sidecar (${dump_path}.sha256)" >&2
  exit 1
fi

dqa_preflight
dqa_require_cmd sha256sum

# Verify checksum before touching the database.
echo "Verifying SHA-256 sidecar..."
(
  cd "$(dirname "${dump_path}")"
  sha256sum --check --status "$(basename "${checksum_path}")"
) || {
  echo "error: SHA-256 checksum mismatch; restore refused" >&2
  exit 1
}

dqa_require_app_stopped_for_restore
dqa_ensure_db_healthy

db_user="$(dqa_db_user)"
db_name="$(dqa_db_name)"

# Fail closed on unexpected identifier characters (defence in depth).
if [[ ! "${db_name}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "error: refuse restore: DQA_DB_NAME is not a safe SQL identifier" >&2
  exit 1
fi
if [[ ! "${db_user}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "error: refuse restore: DQA_DB_USER is not a safe SQL identifier" >&2
  exit 1
fi

container_tmp="/tmp/dqa_restore_$$.dump"

echo "Copying archive into dqa-db for validation/restore..."
dqa_compose cp "${dump_path}" "dqa-db:${container_tmp}"

echo "Validating pg_dump custom-format archive..."
if ! dqa_db_exec pg_restore --list "${container_tmp}" >/dev/null; then
  dqa_db_exec rm -f "${container_tmp}" || true
  echo "error: archive is not a valid pg_dump custom-format file; restore refused" >&2
  exit 1
fi

echo "Terminating sessions and recreating DQA database..."
# Connect to the maintenance DB. Identifiers come only from configured env values.
# Use psql variable quoting (string + identifier) — never pass DQA_DB_PASSWORD.
dqa_db_exec \
  psql \
  --username="${db_user}" \
  --dbname=postgres \
  --set=ON_ERROR_STOP=1 \
  --set="restore_db=${db_name}" \
  --set="restore_owner=${db_user}" \
  --command="SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :'restore_db' AND pid <> pg_backend_pid();" \
  --command='DROP DATABASE IF EXISTS :"restore_db";' \
  --command='CREATE DATABASE :"restore_db" OWNER :"restore_owner";'

echo "Restoring archive with pg_restore..."
# Fresh empty database from DROP/CREATE; restore objects from custom-format archive.
# Do not pipe untrusted SQL text through psql.
if ! dqa_db_exec \
  pg_restore \
  --username="${db_user}" \
  --dbname="${db_name}" \
  --no-owner \
  --role="${db_user}" \
  "${container_tmp}"; then
  dqa_db_exec rm -f "${container_tmp}" || true
  echo "error: pg_restore failed" >&2
  exit 1
fi

dqa_db_exec rm -f "${container_tmp}"

echo "Checking Alembic migration head after restore..."
if ! dqa_compose --profile migrate run --rm --no-deps migrate \
  python alembic/check_at_head.py; then
  echo "error: restored database is not at Alembic head" >&2
  echo "Inspect the dump provenance, then run ./scripts/dqa-migrate.sh only if intended." >&2
  exit 1
fi

echo "Restore complete."
echo "Application services were not started. When ready: ./scripts/dqa-up.sh"
