#!/usr/bin/env bash
# U-02-B-2-B isolated Legacy PostgreSQL -> DQA validation.
# Invoke with "bash scripts/u02b2b/run.sh" rather than "source".
# Errors here cannot terminate the interactive PuTTY shell.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LEGACY="$(printenv DQA_U02_LEGACY_ROOT 2>/dev/null || printf '%s' /tmp/dqa-u02-legacy-pr83.GsdyYQ)"
EXPECTED_LEGACY="c9b88f6f6d14dc2598765efbf6bb41b4771f9b25"
BASE="93f7a64f9ab513dbab403f6cdcd35951f4e7291a"
COMPOSE="$ROOT/scripts/u02b2b/compose.yaml"
PYTHON="$(printenv DQA_U02_DQA_PYTHON 2>/dev/null || printf '%s' "$HOME/dqa/.venv/bin/python")"

fail() { echo "U02B2B FAIL: $*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || fail "docker not installed"
docker compose version >/dev/null 2>&1 || fail "docker compose unavailable"
test -x "$PYTHON" || fail "DQA venv python not executable: $PYTHON"
git -C "$LEGACY" rev-parse --git-dir >/dev/null 2>&1 \
  || fail "Legacy Git checkout not available"
actual="$(git -C "$LEGACY" rev-parse HEAD 2>/dev/null)" \
  || fail "Could not read Legacy HEAD"
test "$actual" = "$EXPECTED_LEGACY" || fail "Legacy HEAD differs from pinned SHA"

for rel in \
  backend/app/services/catalog_package.py \
  backend/app/services/catalog_package_finalizer.py \
  backend/tests/test_catalog_package_finalization.py \
  database/schema_catalog/init/01_init.sql
do
  test -f "$LEGACY/$rel" || fail "Missing pinned Legacy file: $rel"
  blob="$(git -C "$LEGACY" rev-parse "HEAD:$rel" 2>/dev/null)" \
    || fail "Cannot read git blob: $rel"
  work="$(git -C "$LEGACY" hash-object "$LEGACY/$rel")" \
    || fail "Cannot hash pinned file: $rel"
  test "$blob" = "$work" || fail "Modified pinned Legacy file: $rel"
done

test "$(git -C "$ROOT" merge-base "$BASE" HEAD 2>/dev/null)" = "$BASE" \
  || fail "DQA branch not based on expected PR #84 merge commit"

ARTIFACT_DIR="$(mktemp -d /tmp/dqa-u02b2b-evidence.XXXXXX)" \
  || fail "Cannot create isolated fixture artifact directory"
export DQA_U02_LEGACY_ROOT="$LEGACY"
export DQA_U02_DQA_ROOT="$ROOT"
export DQA_U02_ARTIFACT_DIR="$ARTIFACT_DIR"
PROJECT="dqa-u02b2b-$$"

cleanup() {
  result=$?
  docker compose -p "$PROJECT" -f "$COMPOSE" down -v --remove-orphans >/dev/null 2>&1 \
    || echo "WARNING: Docker cleanup failed; inspect project $PROJECT" >&2
  if [ "$result" -eq 0 ]; then
    rm -rf -- "$ARTIFACT_DIR"
  else
    echo "Preserved synthetic evidence for diagnosis: $ARTIFACT_DIR" >&2
  fi
}
trap cleanup EXIT

echo "=== Isolated Legacy DB integration ==="
echo "DQA branch: $(git -C "$ROOT" log -1 --format='%h')"
echo "Legacy pinned: $actual"
echo "Compose project: $PROJECT (NO host ports; disposable volume)"

docker compose -p "$PROJECT" -f "$COMPOSE" config --quiet \
  || fail "Invalid Compose config"
docker compose -p "$PROJECT" -f "$COMPOSE" up --build \
  --abort-on-container-exit --exit-code-from runner runner \
  || fail "Legacy real PostgreSQL finalization failed"

for status in READY WARNING BLOCKED; do
  test -s "$ARTIFACT_DIR/final_$status.zip" \
    || fail "Missing final_$status.zip after Legacy runner"
done

echo "=== DQA v2 Validator + U-02 regression ==="
(
  cd "$ROOT/backend" || exit 1
  DQA_U02B2B_ARTIFACT_DIR="$ARTIFACT_DIR" \
    "$PYTHON" -m pytest -q -rs \
      tests/test_u02b2b_legacy_pg_finalizer.py \
      tests/test_u02b2_legacy_final_zip_validator.py \
      tests/test_u02b_catalog_v2_fingerprint_contract.py \
      tests/test_catalog_package_validation.py
) || fail "DQA integration/regression pytest failed"

git -C "$ROOT" diff --check "$BASE" HEAD \
  || fail "git diff --check failed"
echo "DQA_U02B2B_ACCEPTANCE_PASS"
