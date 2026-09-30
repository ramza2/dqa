#!/usr/bin/env bash
# Restore DQA PostgreSQL from a pg_dump custom-format archive.
#
# Deliberately destructive. Fail closed.
#
# Usage:
#   ./scripts/dqa-restore.sh /path/to/dqa_UTC.dump RESTORE
#
# Order:
#   checksum → app stopped → DB healthy → copy archive →
#   custom-format validation → DROP/CREATE → atomic pg_restore → Alembic head
#
# Safeguards:
# - explicit RESTORE confirmation token (not interactive yes/no)
# - SHA-256 sidecar required and verified
# - PGDMP custom-format magic + pg_restore --list
# - refuse while backend/frontend/migrate are running
# - pg_restore --single-transaction --exit-on-error (no partial schema)
# - no docker compose down -v
# - does not auto-start application services
# - does not restore arbitrary SQL text via psql
# - does not auto-run migrations after a failed/old restore
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

# 1) Verify checksum before touching the database.
echo "Verifying SHA-256 sidecar..."
(
  cd "$(dirname "${dump_path}")"
  sha256sum --check --status "$(basename "${checksum_path}")"
) || {
  echo "error: SHA-256 checksum mismatch; restore refused" >&2
  exit 1
}

# 2) Refuse while application services hold DB sessions.
dqa_require_app_stopped_for_restore

# 3) Ensure dqa-db is healthy (does not start backend/frontend).
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
container_tmp_present=0

cleanup_restore_tmp() {
  # Cleanup failure must not hide the primary restore failure.
  if [[ "${container_tmp_present}" -eq 1 ]]; then
    dqa_db_exec rm -f "${container_tmp}" >/dev/null 2>&1 || true
  fi
}
trap cleanup_restore_tmp EXIT

# 4) Copy archive into dqa-db for validation/restore.
echo "Copying archive into dqa-db for validation/restore..."
dqa_compose cp "${dump_path}" "dqa-db:${container_tmp}"
container_tmp_present=1

# 5) Custom-format / archive validation BEFORE any DROP/CREATE.
echo "Validating PostgreSQL custom-format archive..."
dqa_require_pg_custom_archive "${dump_path}"
if ! dqa_db_exec pg_restore --list "${container_tmp}" >/dev/null; then
  echo "error: archive failed pg_restore --list validation; restore refused" >&2
  exit 1
fi

# 6) Only after validation: terminate sessions and recreate DQA database.
echo "Terminating sessions and recreating DQA database..."
# Connect to the maintenance DB. Identifiers come only from configured env values.
# Use psql variable quoting (string + identifier) — never pass DQA_DB_PASSWORD.
if ! dqa_db_exec \
  psql \
  --username="${db_user}" \
  --dbname=postgres \
  --set=ON_ERROR_STOP=1 \
  --set="restore_db=${db_name}" \
  --set="restore_owner=${db_user}" \
  --command="SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :'restore_db' AND pid <> pg_backend_pid();" \
  --command='DROP DATABASE IF EXISTS :"restore_db";' \
  --command='CREATE DATABASE :"restore_db" OWNER :"restore_owner";'; then
  echo "error: failed to recreate DQA database; restore aborted" >&2
  exit 1
fi

# 7) Atomic restore into the empty database.
echo "Restoring archive with atomic pg_restore..."
# Fresh empty database from DROP/CREATE; restore objects from custom-format archive.
# --single-transaction + --exit-on-error: succeed fully or roll back restored objects.
# Do not pipe untrusted SQL text through psql.
if ! dqa_db_exec \
  pg_restore \
  --username="${db_user}" \
  --dbname="${db_name}" \
  --single-transaction \
  --exit-on-error \
  --no-owner \
  --no-privileges \
  --role="${db_user}" \
  "${container_tmp}"; then
  echo "error: pg_restore failed; database left empty (transaction rolled back)" >&2
  echo "Application was not started. Fix the archive, then retry restore." >&2
  exit 1
fi

# Explicit cleanup before Alembic check; trap remains harmless if already gone.
dqa_db_exec rm -f "${container_tmp}" >/dev/null 2>&1 || true
container_tmp_present=0
trap - EXIT

# 8) Alembic head check only after successful pg_restore.
# Do not auto-run migrations for a failed/old restore.
echo "Checking Alembic migration head after restore..."
if ! dqa_compose --profile migrate run --rm --no-deps migrate \
  python alembic/check_at_head.py; then
  echo "error: restored database is not at Alembic head" >&2
  echo "Inspect the dump provenance, then run ./scripts/dqa-migrate.sh only if intended." >&2
  exit 1
fi

echo "Restore complete."
echo "Application services were not started. When ready: ./scripts/dqa-up.sh"
