#!/usr/bin/env bash
# P30-A: Web/MCP shared-query contract and R-01 read-source regression.
# Offline only; NEVER invoke tests using db_session/db_client fixtures here.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${DQA_P30A_PYTHON:-${HOME}/dqa/.venv/bin/python}"
[[ -x "${PYTHON}" ]] || { echo "P30A_REFUSED: test venv unavailable" >&2; exit 2; }

export APP_ENV=test
export DQA_AUTH_PROVIDER=dev_headers
export DQA_SCHEMA_INSPECTOR_ENABLED=false
export DQA_SCHEMA_SNAPSHOT_REVIEW_ENABLED=false
export DQA_MCP_QUERY_EXECUTION_ENABLED=false
export LLM_BASE_URL=""
export EMBEDDING_BASE_URL=""

cd "${ROOT}/backend"
"${PYTHON}" -m pytest -q -rs \
  tests/test_p30a_web_mcp_offline_execution_parity.py \
  tests/test_r01a_replica_read_safety.py \
  tests/test_r01b_replica_target_screening.py \
  tests/test_r01c_site_target_evidence_review.py \
  tests/test_r01d_offline_policy_isolation.py

echo "DQA_P30A_OFFLINE_PARITY_PASS"
