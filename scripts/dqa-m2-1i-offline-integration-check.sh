#!/usr/bin/env bash
# M2-1I: existing M2-1A..H synthetic offline regression; no Oracle/DEMIS/PG.
# Invoke with bash, never source; no Docker, site network or migration commands.
set -euo pipefail
set +x
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${DQA_M2_1I_PYTHON:-${HOME}/dqa/.venv/bin/python}"
block() { echo "M2_1I_BLOCKED=$1" >&2; exit 2; }
[[ -x "$PYTHON" ]] || block "PYTHON_VENV_MISSING"
command -v npm >/dev/null 2>&1 || block "NPM_UNAVAILABLE"
[[ -d "$ROOT/frontend/node_modules" ]] || block "FRONTEND_NODE_MODULES_MISSING"
[[ -f "$ROOT/backend/tests/test_m2_1h_offline_summary.py" ]] || block "INCOMPATIBLE_WORKTREE"

export APP_ENV=test
export DQA_AUTH_PROVIDER=dev_headers
export DQA_DEV_ORACLE_MOCK_ACTIONS_ENABLED=false
export DQA_SCHEMA_INSPECTOR_ENABLED=false
export DQA_SCHEMA_SNAPSHOT_REVIEW_ENABLED=false
export DQA_MCP_QUERY_EXECUTION_ENABLED=false
export LLM_BASE_URL=""
export EMBEDDING_BASE_URL=""

echo "===== M2-1A..H OFFLINE BACKEND REGRESSION ====="
(
  cd "$ROOT/backend"
  "$PYTHON" -m pytest -q \
    tests/test_m2_1a_explicit_mock_registration.py \
    tests/test_m2_1b_mock_inspector_binding.py \
    tests/test_m2_1c_inspector_privilege_probe_script.py \
    tests/test_m2_1d_offline_metadata_export.py \
    tests/test_m2_1e_offline_provenance.py \
    tests/test_m2_1f_offline_review_draft.py \
    tests/test_m2_1g_offline_snapshot_link.py \
    tests/test_m2_1h_offline_summary.py \
    tests/test_schema_snapshot_review.py \
    tests/test_schema_snapshot_diff.py \
    tests/test_schema_preflight_contract.py \
    tests/test_r01d_offline_policy_isolation.py
)
echo "M2_1I_BACKEND_OFFLINE_PASS"

echo "===== M2-1 OPERATOR UI REGRESSION ====="
(
  cd "$ROOT/frontend"
  npm test -- --run \
    src/test/ConnectionProfiles.test.tsx \
    src/test/MockInspectorPanel.test.tsx \
    src/test/OfflineMetadataSummary.test.tsx \
    src/test/SchemaSnapshotHistory.test.tsx
  npm run build
  npm run lint
)
echo "M2_1I_FRONTEND_OFFLINE_PASS"
echo "M2_1I_INTEGRATION_OFFLINE_PASS"
