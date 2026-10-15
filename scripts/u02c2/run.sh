#!/usr/bin/env bash
# U-02-C-2: use "bash scripts/u02c2/run.sh"; do not source into PuTTY.
# No real Legacy/DEMIS/DQA database access: disposable internal PostgreSQL only.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LEGACY="$(printenv DQA_U02_LEGACY_ROOT 2>/dev/null || printf '%s' /tmp/dqa-u02-legacy-pr83.GsdyYQ)"
EXPECTED="c9b88f6f6d14dc2598765efbf6bb41b4771f9b25"
BASE="115c567c5248d9a3c1f84b67a2fb4bebc1475bec"
PYTHON="$(printenv DQA_U02_DQA_PYTHON 2>/dev/null || printf '%s' "$HOME/dqa/.venv/bin/python")"
COMPOSE="$ROOT/scripts/u02c2/compose.yaml"

fail() { echo "U02C2 FAIL: $*" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || fail "docker missing"
docker compose version >/dev/null 2>&1 || fail "docker compose unavailable"
test -x "$PYTHON" || fail "DQA venv unavailable"
git -C "$LEGACY" rev-parse --git-dir >/dev/null 2>&1 \
  || fail "Pinned Legacy checkout missing"
actual="$(git -C "$LEGACY" rev-parse HEAD 2>/dev/null)" || fail "Legacy HEAD missing"
test "$actual" = "$EXPECTED" || fail "Legacy SHA mismatch"

for rel in \
  backend/app/models/catalog.py \
  backend/app/models/catalog_category.py \
  backend/app/models/catalog_history.py \
  backend/app/models/catalog_validation.py \
  backend/tests/test_catalog_package_finalization.py \
  database/schema_catalog/init/01_init.sql
do
  test -f "$LEGACY/$rel" || fail "Legacy file missing"
  blob="$(git -C "$LEGACY" rev-parse "HEAD:$rel" 2>/dev/null)" \
    || fail "Legacy Git blob missing"
  actual_blob="$(git -C "$LEGACY" hash-object "$LEGACY/$rel")" \
    || fail "Legacy file hash failed"
  test "$actual_blob" = "$blob" || fail "Legacy file modified: $rel"
done

test "$(git -C "$ROOT" merge-base "$BASE" HEAD 2>/dev/null)" = "$BASE" \
  || fail "DQA branch is not descendant of merged PR #86"

ARTIFACT_DIR="$(mktemp -d /tmp/dqa-u02c2-evidence.XXXXXX)" \
  || fail "Temporary artifact directory failed"
export DQA_U02_LEGACY_ROOT="$LEGACY"
export DQA_U02_DQA_ROOT="$ROOT"
export DQA_U02_ARTIFACT_DIR="$ARTIFACT_DIR"
PROJECT="dqa-u02c2-$$"

cleanup() {
  result=$?
  docker compose -p "$PROJECT" -f "$COMPOSE" down -v --remove-orphans >/dev/null 2>&1 \
    || echo "WARNING: inspect orphan test project $PROJECT" >&2
  if [ "$result" -eq 0 ]; then
    rm -rf -- "$ARTIFACT_DIR"
  else
    echo "Synthetic-only evidence kept: $ARTIFACT_DIR" >&2
  fi
}
trap cleanup EXIT

echo "=== U-02-C-2 isolated read-only Legacy inventory ==="
echo "DQA branch: $(git -C "$ROOT" log -1 --format='%h')"
echo "Legacy SHA: $EXPECTED"
echo "Disposable Compose project: $PROJECT; no host ports"

docker compose -p "$PROJECT" -f "$COMPOSE" config --quiet \
  || fail "Compose configuration invalid"
docker compose -p "$PROJECT" -f "$COMPOSE" up --build \
  --abort-on-container-exit --exit-code-from collector collector \
  || fail "Isolated SELECT-only inventory collector failed"

test -s "$ARTIFACT_DIR/u02c2_inventory.json" || fail "Inventory JSON not generated"

echo "=== DQA static and PG evidence contract tests ==="
(
  cd "$ROOT/backend" || exit 1
  DQA_U02C2_ARTIFACT_DIR="$ARTIFACT_DIR" \
  DQA_U02_LEGACY_ROOT="$LEGACY" \
    "$PYTHON" -m pytest -q -rs \
      tests/test_u02c2_inventory_readonly.py \
      tests/test_u02c_cutover_inventory_contract.py
) || fail "DQA tests failed"
git -C "$ROOT" diff --check "$BASE" HEAD || fail "git diff --check failed"
echo "DQA_U02C2_ACCEPTANCE_PASS"
