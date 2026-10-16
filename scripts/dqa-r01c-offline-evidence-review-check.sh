#!/usr/bin/env bash
# R-01-C: pure offline evidence-draft review + R-01-A/B regression only.
# Do not run DB integration tests, Docker, live Oracle, real DEMIS or DNS.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${DQA_R01C_PYTHON:-${HOME}/dqa/.venv/bin/python}"
if [[ ! -x "${PYTHON}" ]]; then
  echo "R01C_REFUSED: Python venv unavailable at ${PYTHON}" >&2
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
  tests/test_r01b_replica_target_screening.py \
  tests/test_r01c_site_target_evidence_review.py
echo "DQA_R01C_OFFLINE_EVIDENCE_REVIEW_PASS"
