#!/usr/bin/env bash
# R-01-B offline structural-screening and R-01-A regression acceptance.
# No Docker, PostgreSQL, Oracle, DEMIS, DNS/hosts or credentials are accessed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${DQA_R01B_PYTHON:-${HOME}/dqa/.venv/bin/python}"
if [[ ! -x "${PYTHON}" ]]; then
  echo "R01B_REFUSED: expected Python venv at ${PYTHON}" >&2
  exit 2
fi
export APP_ENV=test
export DQA_AUTH_PROVIDER=dev_headers
export DQA_SCHEMA_INSPECTOR_ENABLED=false
export DQA_SCHEMA_SNAPSHOT_REVIEW_ENABLED=false
export LLM_BASE_URL=""
export EMBEDDING_BASE_URL=""

cd "${ROOT}/backend"
"${PYTHON}" -m pytest -q -rs \
  tests/test_r01a_replica_read_safety.py \
  tests/test_r01b_replica_target_screening.py
echo "DQA_R01B_OFFLINE_TARGET_POLICY_PASS"
