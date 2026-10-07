#!/usr/bin/env bash
# Read-only Production Readiness Report for one Catalog source + environment.
#
# Does NOT:
#   - resolve DEMIS credentials
#   - open DEMIS sockets / run live probe
#   - mutate schema or application data
#   - persist readiness or probe results
#
# Preferred workflow:
#   ./scripts/dqa-migrate.sh
#   ./scripts/dqa-up.sh
#   ./scripts/dqa-readiness.sh --source-name ... --environment ...
#   # explicit live probe remains a separate administrator action
#
# Exit codes:
#   0 — report generated and overall READY
#   1 — NOT_READY / blocked / inspection failure / invalid args
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=dqa-common.sh
source "${SCRIPT_DIR}/dqa-common.sh"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/dqa-readiness.sh --source-name <name> --environment <env> [--json]

Read-only Production Readiness Report. Never probes DEMIS or prints secrets.
EOF
}

SOURCE_NAME=""
ENVIRONMENT=""
JSON_FLAG=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source-name)
      SOURCE_NAME="${2:-}"
      shift 2
      ;;
    --environment)
      ENVIRONMENT="${2:-}"
      shift 2
      ;;
    --json)
      JSON_FLAG=(--json)
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "${SOURCE_NAME}" || -z "${ENVIRONMENT}" ]]; then
  echo "error: --source-name and --environment are required" >&2
  usage >&2
  exit 1
fi

dqa_preflight
dqa_ensure_db_healthy

echo "Building migrate image for readiness inspection (read-only)..."
dqa_compose build migrate >/dev/null

# Reuse migrate/backend image Python runtime; never start frontend/backend for this.
set +e
dqa_compose --profile migrate run --rm --no-deps migrate \
  python -m app.cli.production_readiness \
  --source-name "${SOURCE_NAME}" \
  --environment "${ENVIRONMENT}" \
  "${JSON_FLAG[@]}"
status=$?
set -e

exit "${status}"
