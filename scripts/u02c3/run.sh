#!/usr/bin/env bash
# U-02-C-3: disposable PG backup -> distinct DB restore -> validation.
# Invoke as bash .../run.sh, NEVER source into PuTTY. No host DB ports.
set -uo pipefail
umask 077

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LEGACY="$(printenv DQA_U02_LEGACY_ROOT 2>/dev/null || printf '%s' /tmp/dqa-u02-legacy-pr83.GsdyYQ)"
EXPECTED="c9b88f6f6d14dc2598765efbf6bb41b4771f9b25"
BASE="060d2ffefc1abdf4eab49c9d3b690732dce19108"
PYTHON="$(printenv DQA_U02_DQA_PYTHON 2>/dev/null || printf '%s' "$HOME/dqa/.venv/bin/python")"
COMPOSE="$ROOT/scripts/u02c3/compose.yaml"

fail() { echo "U02C3 FAIL: $*" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || fail "docker not found"
docker compose version >/dev/null 2>&1 || fail "docker compose unavailable"
command -v sha256sum >/dev/null 2>&1 || fail "sha256sum not found"
test -x "$PYTHON" || fail "DQA Python venv missing"
git -C "$LEGACY" rev-parse --git-dir >/dev/null 2>&1 \
  || fail "Pinned Legacy checkout absent"
test "$(git -C "$LEGACY" rev-parse HEAD 2>/dev/null)" = "$EXPECTED" \
  || fail "Legacy SHA changed"

for rel in \
  backend/app/models/catalog.py \
  backend/app/models/catalog_category.py \
  backend/app/models/catalog_history.py \
  backend/app/models/catalog_validation.py \
  backend/app/services/catalog_package.py \
  backend/app/services/catalog_package_finalizer.py \
  backend/tests/test_catalog_package_finalization.py \
  database/schema_catalog/init/01_init.sql
do
  test -f "$LEGACY/$rel" || fail "Missing Legacy file: $rel"
  blob="$(git -C "$LEGACY" rev-parse "HEAD:$rel" 2>/dev/null)" \
    || fail "Cannot read pinned blob: $rel"
  work="$(git -C "$LEGACY" hash-object "$LEGACY/$rel")" \
    || fail "Cannot hash pinned file: $rel"
  test "$blob" = "$work" || fail "Modified Legacy file: $rel"
done

test "$(git -C "$ROOT" merge-base "$BASE" HEAD 2>/dev/null)" = "$BASE" \
  || fail "Unexpected DQA base"

ARTIFACT_DIR="$(mktemp -d /tmp/dqa-u02c3-evidence.XXXXXX)" \
  || fail "Cannot create private synthetic artifact dir"
export DQA_U02_LEGACY_ROOT="$LEGACY"
export DQA_U02_DQA_ROOT="$ROOT"
export DQA_U02_ARTIFACT_DIR="$ARTIFACT_DIR"
PROJECT="dqa-u02c3-$$"

cleanup() {
  result=$?
  docker compose -p "$PROJECT" -f "$COMPOSE" down -v --remove-orphans >/dev/null 2>&1 \
    || { echo "U02C3 WARNING: manual docker cleanup required for $PROJECT" >&2; result=1; }
  if [ "$result" -eq 0 ]; then
    rm -rf -- "$ARTIFACT_DIR" || result=1
  else
    echo "Only synthetic temporary backup evidence retained: $ARTIFACT_DIR" >&2
  fi
  exit "$result"
}
trap cleanup EXIT

echo "=== U-02-C-3 SYNTHETIC ONLY: isolated PostgreSQL backup/restore ==="
echo "Legacy pin $EXPECTED; DQA HEAD $(git -C "$ROOT" log -1 --format='%h')"
echo "Disposable Compose project: $PROJECT (no published ports)"

docker compose -p "$PROJECT" -f "$COMPOSE" config --quiet \
  || fail "Compose invalid"
docker compose -p "$PROJECT" -f "$COMPOSE" up -d catalog-db \
  || fail "Cannot start disposable DB"
docker compose -p "$PROJECT" -f "$COMPOSE" run --build --rm seed \
  || fail "Cannot create synthetic source fixtures"
test -s "$ARTIFACT_DIR/u02c2_inventory.json" || fail "Inventory not generated"
test -s "$ARTIFACT_DIR/legacy_final_ready.zip" || fail "Original Legacy ZIP missing"

# Backup one synthetic DB via PostgreSQL native custom format, into private
# temporary host directory. No production database, credentials, ports or DNS.
BACKUP="$ARTIFACT_DIR/legacy_catalog.pgcustom"
docker compose -p "$PROJECT" -f "$COMPOSE" exec -T catalog-db \
  pg_dump -U u02b2b_user -d u02b2b_catalog --format=custom \
  --no-owner --no-acl > "$BACKUP" \
  || fail "Synthetic pg_dump failed"
test -s "$BACKUP" || fail "Synthetic backup empty"
docker compose -p "$PROJECT" -f "$COMPOSE" exec -T catalog-db \
  pg_restore --list < "$BACKUP" > /dev/null \
  || fail "PG custom backup unreadable"
BACKUP_SHA="$(sha256sum "$BACKUP" | cut -d' ' -f1)"

# Restore ONLY into a fresh, different DB in the same throwaway container.
docker compose -p "$PROJECT" -f "$COMPOSE" exec -T catalog-db \
  createdb -U u02b2b_user -T template0 u02c3_restore \
  || fail "Restore DB creation failed"
docker compose -p "$PROJECT" -f "$COMPOSE" exec -T catalog-db \
  pg_restore -U u02b2b_user -d u02c3_restore --no-owner --no-acl \
  --exit-on-error < "$BACKUP" \
  || fail "Restore to disposable DB failed"
test "$(sha256sum "$BACKUP" | cut -d' ' -f1)" = "$BACKUP_SHA" \
  || fail "PG backup changed after restore"

# Re-grant SELECT in the RESTORED database only; the separate reader already
# exists in this throwaway PostgreSQL cluster. No DML/DDL grants.
docker compose -p "$PROJECT" -f "$COMPOSE" exec -T catalog-db \
  psql -X -v ON_ERROR_STOP=1 -U u02b2b_user -d u02c3_restore \
  -c "GRANT CONNECT ON DATABASE u02c3_restore TO u02c2_reader; GRANT USAGE ON SCHEMA public TO u02c2_reader; GRANT SELECT ON ALL TABLES IN SCHEMA public TO u02c2_reader;" \
  > /dev/null || fail "Cannot grant test restore SELECT-only access"

docker compose -p "$PROJECT" -f "$COMPOSE" run --rm verify \
  || fail "Restored data diff/role verification failed"
test -s "$ARTIFACT_DIR/restore_verified.json" || fail "Restore proof missing"

(
  cd "$ROOT/backend" || exit 1
  "$PYTHON" - "$ARTIFACT_DIR" <<'PY'
import json
import sys
from pathlib import Path
from tests.u02c3_backup_gate import build_manifest, verify_manifest
directory = Path(sys.argv[1])
manifest = build_manifest(directory)
verify_manifest(directory, manifest)
(directory / "rehearsal_manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print("SYNTHETIC_BACKUP_RESTORE_MANIFEST_SEALED")
PY
) || fail "Backup evidence sealing failed"

echo "=== DQA offline+synthetic restored evidence acceptance ==="
(
  cd "$ROOT/backend" || exit 1
  DQA_U02C3_ARTIFACT_DIR="$ARTIFACT_DIR" \
  DQA_U02C2_ARTIFACT_DIR="$ARTIFACT_DIR" \
  DQA_U02_LEGACY_ROOT="$LEGACY" \
    "$PYTHON" -m pytest -q -rs \
      tests/test_u02c3_backup_restore.py \
      tests/test_u02c2_inventory_readonly.py \
      tests/test_u02c_cutover_inventory_contract.py
) || fail "DQA rehearsal regression failed"

git -C "$ROOT" diff --check "$BASE" HEAD || fail "diff --check failed"
echo "DQA_U02C3_ACCEPTANCE_PASS"
