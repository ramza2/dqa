#!/usr/bin/env bash
# Stop on-prem Compose services.
# Does NOT delete the PostgreSQL named volume by default.
# Does NOT auto-prune images/networks.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=dqa-common.sh
source "${SCRIPT_DIR}/dqa-common.sh"

dqa_preflight

if [[ "${1:-}" == "--volumes" ]]; then
  echo "error: refusing destructive volume delete. Remove data only with an explicit operator-reviewed procedure." >&2
  exit 1
fi

dqa_compose down --remove-orphans
echo "Services stopped. Named volume dqa_pgdata was preserved."
