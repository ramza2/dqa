#!/usr/bin/env bash
# Read-only aggregate inspection of query_audit_events retention window.
#
# Prints only:
#   - oldest created_at
#   - newest created_at
#   - total event count
#
# Does NOT print actor IDs, source names, audit IDs, parameter names, or results.
# Does NOT delete or purge anything.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=dqa-common.sh
source "${SCRIPT_DIR}/dqa-common.sh"

dqa_preflight
dqa_ensure_db_healthy

db_user="$(dqa_db_user)"
db_name="$(dqa_db_name)"

echo "Audit retention status (aggregates only; no row details)..."

# Aggregate-only SQL. No identifiers or row payloads selected.
aggregate_row="$(
  dqa_db_exec \
    psql \
    --username="${db_user}" \
    --dbname="${db_name}" \
    --set=ON_ERROR_STOP=1 \
    --tuples-only \
    --no-align \
    --field-separator='|' \
    <<'SQL'
SELECT
  COALESCE(MIN(created_at)::text, 'n/a'),
  COALESCE(MAX(created_at)::text, 'n/a'),
  COUNT(*)::text
FROM query_audit_events;
SQL
)"

oldest="$(printf '%s' "${aggregate_row}" | cut -d'|' -f1 | tr -d '[:space:]')"
newest="$(printf '%s' "${aggregate_row}" | cut -d'|' -f2 | tr -d '[:space:]')"
total="$(printf '%s' "${aggregate_row}" | cut -d'|' -f3 | tr -d '[:space:]')"

if [[ -z "${oldest}" || -z "${newest}" || -z "${total}" ]]; then
  echo "error: unexpected empty aggregate query output" >&2
  exit 1
fi

echo "oldest_created_at: ${oldest}"
echo "newest_created_at: ${newest}"
echo "total_event_count: ${total}"
echo "NOTE: Retention duration is site policy and is not hardcoded."
echo "No automatic purge is performed by this script."
