#!/usr/bin/env bash
# Create a consistent DQA PostgreSQL backup (application DB only).
#
# Output:
#   ${DQA_BACKUP_DIR:-./backups}/dqa_<UTC-timestamp>.dump
#   matching .sha256 sidecar
#
# Uses pg_dump -Fc inside the dqa-db container (no host PostgreSQL client).
# Does not back up DEMIS. Does not echo secrets.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=dqa-common.sh
source "${SCRIPT_DIR}/dqa-common.sh"

dqa_preflight
dqa_require_cmd sha256sum

dqa_ensure_db_healthy
dqa_require_migrations_at_head

backup_dir="$(dqa_backup_dir)"
mkdir -p "${backup_dir}"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
dump_name="dqa_${timestamp}.dump"
dump_path="${backup_dir%/}/${dump_name}"
checksum_path="${dump_path}.sha256"
container_tmp="/tmp/${dump_name}"

db_user="$(dqa_db_user)"
db_name="$(dqa_db_name)"

echo "Creating DQA PostgreSQL backup (custom format)..."
# pg_dump runs inside the container; local socket auth does not require exposing
# DQA_DB_PASSWORD on the host command line.
dqa_db_exec \
  pg_dump \
  --username="${db_user}" \
  --dbname="${db_name}" \
  --format=custom \
  --file="${container_tmp}"

# Copy archive to the operator-controlled host directory, then remove temp file.
dqa_compose cp "dqa-db:${container_tmp}" "${dump_path}"
dqa_db_exec rm -f "${container_tmp}"

if [[ ! -s "${dump_path}" ]]; then
  echo "error: backup file missing or empty after pg_dump" >&2
  exit 1
fi

# Validate archive type without restoring.
dqa_compose cp "${dump_path}" "dqa-db:${container_tmp}"
if ! dqa_db_exec pg_restore --list "${container_tmp}" >/dev/null; then
  dqa_db_exec rm -f "${container_tmp}" || true
  echo "error: backup archive failed pg_restore --list validation" >&2
  exit 1
fi
dqa_db_exec rm -f "${container_tmp}"

(
  cd "$(dirname "${dump_path}")"
  sha256sum "$(basename "${dump_path}")" >"$(basename "${checksum_path}")"
)

echo "Backup complete."
echo "archive: ${dump_path}"
echo "sha256:  ${checksum_path}"
echo "NOTE: Backup may contain Catalog/template/audit operational metadata."
echo "Store only in an approved protected location. Encryption is not applied by this script."
