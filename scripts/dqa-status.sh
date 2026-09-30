#!/usr/bin/env bash
# Show on-prem Compose service status (no secrets).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=dqa-common.sh
source "${SCRIPT_DIR}/dqa-common.sh"

dqa_preflight
dqa_compose ps
echo
echo "Backend readiness (inside Compose network):"
dqa_compose exec -T backend \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=4).read().decode())" \
  || echo "backend not ready"
echo
echo "Frontend HTTP check:"
dqa_compose exec -T frontend wget -q -O - http://127.0.0.1/ >/dev/null \
  && echo "frontend OK" \
  || echo "frontend not ready"
