#!/usr/bin/env bash
# Dry-run listing helper for DQA backup archives.
#
# Lists dump files under DQA_BACKUP_DIR with age metadata.
# Does NOT delete anything. Backup retention is site policy.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=dqa-common.sh
source "${SCRIPT_DIR}/dqa-common.sh"

# Env file is optional for listing when DQA_BACKUP_DIR is already exported.
if [[ -z "${DQA_BACKUP_DIR:-}" && ! -f "${DQA_ENV_FILE}" ]]; then
  dqa_require_env_file
fi

backup_dir="$(dqa_backup_dir)"

if [[ ! -d "${backup_dir}" ]]; then
  echo "backup_dir: ${backup_dir}"
  echo "status: directory does not exist (no backups yet)"
  exit 0
fi

echo "backup_dir: ${backup_dir}"
echo "mode: dry-run listing only (no deletion)"
echo "---"

shopt -s nullglob
dumps=("${backup_dir%/}"/dqa_*.dump)
if ((${#dumps[@]} == 0)); then
  echo "(no dqa_*.dump archives found)"
  exit 0
fi

# Newest first by filename (UTC timestamp in name).
printf '%s\n' "${dumps[@]}" | sort -r | while IFS= read -r dump; do
  base="$(basename "${dump}")"
  size="$(wc -c <"${dump}" | tr -d ' ')"
  if mtime_epoch="$(stat -c %Y "${dump}" 2>/dev/null)"; then
    mtime="$(date -u -d "@${mtime_epoch}" +%Y-%m-%dT%H:%M:%SZ)"
  else
    mtime="unknown"
  fi
  sidecar="missing"
  if [[ -f "${dump}.sha256" ]]; then
    sidecar="present"
  fi
  echo "archive=${base} bytes=${size} mtime_utc=${mtime} sha256_sidecar=${sidecar}"
done

echo "---"
echo "NOTE: This helper never deletes backups. Apply site retention policy manually."
