#!/usr/bin/env bash
# M5-L1D frontend runtime regression against the existing on-prem dev image.
# Read-only test-source mount; no backend, DB, network, or service mutation.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="dqa-onprem-frontend:latest"
die() { printf 'DQA_M5_L1D_FRONTEND_TEST_REFUSED: %s\n' "$*" >&2; exit 2; }

[[ "$#" -eq 0 ]] || die "no arguments accepted"
command -v docker >/dev/null 2>&1 || die "docker is required"

for name in \
  LLMConnectionDraftPanel.test.tsx \
  IntegrationSettingsPortal.test.tsx \
  setup.ts; do
  [[ -f "$ROOT/frontend/src/test/$name" ]] || die "test source missing: $name"
done

docker image inspect "$IMAGE" >/dev/null 2>&1 ||
  die "local frontend dev image missing (build it with the on-prem dev Compose overlay)"

# The frontend/.dockerignore intentionally excludes test sources from the
# image. Mount only tests from the matching host checkout; do not rebuild,
# change Compose roles, or expose dev administrator identity on the LAN.
docker run --rm --network none \
  --mount "type=bind,src=$ROOT/frontend/src/test,dst=/app/src/test,readonly" \
  --entrypoint /app/node_modules/.bin/vitest \
  "$IMAGE" \
  run \
  src/test/LLMConnectionDraftPanel.test.tsx \
  src/test/IntegrationSettingsPortal.test.tsx

echo "DQA_M5_L1D_FRONTEND_RUNTIME_TEST_PASS"
