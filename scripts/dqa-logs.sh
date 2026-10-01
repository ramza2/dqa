#!/usr/bin/env bash
# Tail on-prem Compose logs. Does not echo env/secrets files.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=dqa-common.sh
source "${SCRIPT_DIR}/dqa-common.sh"

dqa_preflight
# Pass through optional service names / flags after -- .
dqa_compose logs --tail="${DQA_LOG_TAIL:-200}" "$@"
