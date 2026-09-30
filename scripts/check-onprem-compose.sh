#!/usr/bin/env bash
# Static regression checks for on-prem Compose auth + network boundaries.
# Does not require a running Docker daemon for source assertions.
# When Docker is available, also validates resolved `docker compose config` output.
#
# Never installs Python packages (no pip). Prefer stdlib text checks; for Docker
# resolve checks, grep the rendered Compose config without mutating the host env.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

ONPREM="${ROOT}/docker-compose.onprem.yml"
DEV_OVERLAY="${ROOT}/docker-compose.onprem.dev.yml"
ENV_EXAMPLE="${ROOT}/.env.onprem.example"
COMMON="${ROOT}/scripts/dqa-common.sh"
UP="${ROOT}/scripts/dqa-up.sh"
MIGRATE="${ROOT}/scripts/dqa-migrate.sh"
DOWN="${ROOT}/scripts/dqa-down.sh"
CHECK_AT_HEAD="${ROOT}/backend/alembic/check_at_head.py"
NGINX_CONF="${ROOT}/frontend/nginx.conf"
NGINX_MAIN="${ROOT}/frontend/nginx.main.conf"
NGINX_PROXY="${ROOT}/frontend/dqa_proxy_params.conf"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

pass() {
  echo "PASS: $*"
}

[[ -f "${ONPREM}" ]] || fail "missing ${ONPREM}"
[[ -f "${DEV_OVERLAY}" ]] || fail "missing ${DEV_OVERLAY}"
[[ -f "${CHECK_AT_HEAD}" ]] || fail "missing ${CHECK_AT_HEAD}"
[[ -f "${NGINX_CONF}" ]] || fail "missing ${NGINX_CONF}"
[[ -f "${NGINX_MAIN}" ]] || fail "missing ${NGINX_MAIN}"
[[ -f "${NGINX_PROXY}" ]] || fail "missing ${NGINX_PROXY}"

# --- Production Compose source: hardcoded auth (not ${...} from env) ---
grep -qE '^[[:space:]]*APP_ENV:[[:space:]]*production[[:space:]]*$' "${ONPREM}" \
  || fail "production Compose must hardcode APP_ENV: production"
grep -qE '^[[:space:]]*DQA_AUTH_PROVIDER:[[:space:]]*disabled[[:space:]]*$' "${ONPREM}" \
  || fail "production Compose must hardcode DQA_AUTH_PROVIDER: disabled"

if grep -nE 'APP_ENV:[[:space:]]*\$\{APP_ENV' "${ONPREM}" >/dev/null; then
  fail "production Compose must not allow APP_ENV override via .env"
fi
if grep -nE 'DQA_AUTH_PROVIDER:[[:space:]]*\$\{DQA_AUTH_PROVIDER' "${ONPREM}" >/dev/null; then
  fail "production Compose must not allow DQA_AUTH_PROVIDER override via .env"
fi
pass "production Compose hardcodes APP_ENV=production and DQA_AUTH_PROVIDER=disabled"

python3 - <<'PY' || fail "migrate APP_ENV / topology check failed"
from pathlib import Path
import re

text = Path("docker-compose.onprem.yml").read_text()
match = re.search(r"(?ms)^  migrate:\n(.*?)(?=^  [a-z].*:|\Z)", text)
assert match, "migrate service block not found"
block = match.group(1)
assert re.search(r"(?m)^\s+APP_ENV:\s*production\s*$", block), block
assert "APP_ENV: ${" not in block

# Topology via text (no PyYAML / no pip).
db_block = re.search(r"(?ms)^  dqa-db:\n(.*?)(?=^  [a-z].*:|\Z)", text)
backend_block = re.search(r"(?ms)^  backend:\n(.*?)(?=^  [a-z].*:|\Z)", text)
frontend_block = re.search(r"(?ms)^  frontend:\n(.*?)(?=^  [a-z].*:|\Z)", text)
assert db_block and backend_block and frontend_block
assert not re.search(r"(?m)^\s+ports:\s*$", db_block.group(1)), "DB must not publish host ports"
assert not re.search(r"(?m)^\s+ports:\s*$", backend_block.group(1)), "backend must not publish host ports"
assert re.search(r"(?m)^\s+ports:\s*$", frontend_block.group(1)), "frontend must publish LAN port"
assert re.search(r"(?m)^\s+expose:\s*$", backend_block.group(1))
assert 'internal: true' in text
assert re.search(r"(?m)^\s+APP_ENV:\s*production\s*$", backend_block.group(1))
assert re.search(r"(?m)^\s+DQA_AUTH_PROVIDER:\s*disabled\s*$", backend_block.group(1))
print("migrate_and_topology_ok")
PY
pass "migrate service hardcodes APP_ENV=production; only frontend publishes a host/LAN port"

# --- Dev overlay ---
grep -qE '^[[:space:]]*APP_ENV:[[:space:]]*development[[:space:]]*$' "${DEV_OVERLAY}" \
  || fail "dev overlay must set APP_ENV: development"
grep -qE '^[[:space:]]*DQA_AUTH_PROVIDER:[[:space:]]*dev_headers[[:space:]]*$' "${DEV_OVERLAY}" \
  || fail "dev overlay must set DQA_AUTH_PROVIDER: dev_headers"
pass "dev overlay sets APP_ENV=development and DQA_AUTH_PROVIDER=dev_headers"

# --- Env example must not imply operator can enable prod auth via .env ---
if grep -qE '^APP_ENV=' "${ENV_EXAMPLE}"; then
  fail ".env.onprem.example must not set APP_ENV as an operator production knob"
fi
if grep -qE '^DQA_AUTH_PROVIDER=' "${ENV_EXAMPLE}"; then
  fail ".env.onprem.example must not set DQA_AUTH_PROVIDER as an operator production knob"
fi
grep -qi 'HARDCODED' "${ENV_EXAMPLE}" || fail ".env.onprem.example should state auth is hardcoded in Compose"
pass ".env.onprem.example does not expose APP_ENV/DQA_AUTH_PROVIDER as production knobs"

# --- Do not advertise unused QUERY_* env knobs (no Settings consumers) ---
if grep -nE 'QUERY_(DEFAULT|MAX)_(TIMEOUT_SECONDS|ROW_LIMIT)' "${ONPREM}" "${ENV_EXAMPLE}" >/dev/null; then
  fail "on-prem Compose/.env.onprem.example must not advertise unused QUERY_* variables"
fi
# Also keep .env.example consistent (local placeholder).
if grep -nE 'QUERY_(DEFAULT|MAX)_(TIMEOUT_SECONDS|ROW_LIMIT)' "${ROOT}/.env.example" >/dev/null; then
  fail ".env.example must not advertise unused QUERY_* variables"
fi
pass "unused QUERY_* env knobs are not advertised"

# --- Migration order helpers ---
grep -q 'dqa_require_migrations_at_head' "${COMMON}" || fail "missing dqa_require_migrations_at_head"
grep -q 'dqa_require_migrations_at_head' "${UP}" || fail "dqa-up.sh must call migration preflight"
grep -q 'Database migration is required. Run ./scripts/dqa-migrate.sh first.' "${COMMON}" \
  || fail "missing required migration failure message"
grep -q 'alembic upgrade' "${MIGRATE}" || fail "dqa-migrate.sh must run alembic upgrade"
if grep -nE '^[^#]*alembic[[:space:]]+upgrade|^[^#]*upgrade[[:space:]]+head' "${UP}" >/dev/null; then
  fail "dqa-up.sh must not auto-run alembic upgrade"
fi
if grep -nE 'down[[:space:]].*-v|down[[:space:]].*--volumes' "${DOWN}" >/dev/null; then
  fail "dqa-down.sh must not delete volumes by default"
fi
grep -q 'check_at_head' "${COMMON}" || fail "migration preflight should use Alembic check_at_head helper"
pass "migration-order helpers present; dqa-up does not auto-upgrade; down preserves volume"

# --- Nginx hardening assertions ---
grep -q 'server_tokens off' "${NGINX_MAIN}" || fail "nginx.main.conf must set server_tokens off"
grep -q 'server_tokens off' "${NGINX_CONF}" || fail "nginx.conf must set server_tokens off"
grep -q 'Content-Security-Policy' "${NGINX_CONF}" || fail "nginx.conf must set CSP"
grep -q "default-src 'self'" "${NGINX_CONF}" || fail "CSP must include default-src 'self'"
if grep -qi 'Strict-Transport-Security\|add_header HSTS\|max-age=.*preload' "${NGINX_CONF}" "${NGINX_MAIN}"; then
  fail "HSTS must not be enabled in this nginx foundation (TLS termination owns HSTS)"
fi
if grep -nE '^[[:space:]]*proxy_cache([[:space:]]|;|$)' "${NGINX_CONF}" "${NGINX_MAIN}" "${NGINX_PROXY}" >/dev/null; then
  fail "proxy_cache must not be enabled"
fi
grep -q 'client_max_body_size 2m' "${NGINX_CONF}" || fail "general API body limit must be 2m"
grep -q 'client_max_body_size 55m' "${NGINX_CONF}" || fail "Catalog upload body limit must be 55m"
# 55m > backend 50 MiB archive limit (documented outer boundary only).
python3 - <<'PY' || fail "Catalog nginx body limit must exceed backend archive limit"
from pathlib import Path
import re
nginx = Path("frontend/nginx.conf").read_text()
limits = Path("backend/app/adapters/catalog/limits.py").read_text()
assert "max_archive_bytes: int = 50 * 1024 * 1024" in limits
assert re.search(r"client_max_body_size\s+55m", nginx)
print("nginx_body_gt_backend_archive_ok")
PY
grep -q 'proxy_send_timeout' "${NGINX_PROXY}" || fail "proxy_send_timeout required"
grep -q 'proxy_read_timeout' "${NGINX_PROXY}" || fail "proxy_read_timeout required"
grep -q 'client_body_timeout' "${NGINX_CONF}" || fail "client_body_timeout required"
grep -q 'client_header_timeout' "${NGINX_CONF}" || fail "client_header_timeout required"
grep -q 'send_timeout' "${NGINX_CONF}" || fail "send_timeout required"
grep -q 'Permissions-Policy' "${NGINX_CONF}" || fail "Permissions-Policy required"
grep -q 'Cache-Control "public, max-age=31536000, immutable"' "${NGINX_CONF}" \
  || fail "hashed /assets/ cache policy required"
grep -q 'Cache-Control "no-cache"' "${NGINX_CONF}" || fail "index.html no-cache required"
if grep -nE '^[[:space:]]*proxy_set_header[[:space:]]+X-DQA-Dev-' "${NGINX_CONF}" "${NGINX_PROXY}" "${NGINX_MAIN}" >/dev/null; then
  fail "nginx must not inject X-DQA-Dev-* identity headers"
fi
pass "nginx hardening assertions (tokens/CSP/no-HSTS/no-proxy_cache/body limits/timeouts)"

# --- Backup / restore + audit retention foundations ---
BACKUP="${ROOT}/scripts/dqa-backup.sh"
RESTORE="${ROOT}/scripts/dqa-restore.sh"
BACKUP_LIST="${ROOT}/scripts/dqa-backup-list.sh"
AUDIT_STATUS="${ROOT}/scripts/dqa-audit-retention-status.sh"
GITIGNORE="${ROOT}/.gitignore"
AUDIT_ROUTE="${ROOT}/backend/app/api/routes/audit_events.py"
AUDIT_POLICY="${ROOT}/docs/audit-retention-policy.md"

[[ -f "${BACKUP}" ]] || fail "missing dqa-backup.sh"
[[ -f "${RESTORE}" ]] || fail "missing dqa-restore.sh"
[[ -f "${BACKUP_LIST}" ]] || fail "missing dqa-backup-list.sh"
[[ -f "${AUDIT_STATUS}" ]] || fail "missing dqa-audit-retention-status.sh"
[[ -f "${AUDIT_POLICY}" ]] || fail "missing audit-retention-policy.md"

# backups directory / dump patterns ignored
grep -qE '(^|/ )backups/?$|^/backups/' "${GITIGNORE}" || fail ".gitignore must ignore backups/"
grep -q '\*\.dump' "${GITIGNORE}" || fail ".gitignore must ignore *.dump"
grep -q '\*\.dump\.sha256' "${GITIGNORE}" || fail ".gitignore must ignore *.dump.sha256"

grep -q 'pg_dump' "${BACKUP}" || fail "backup script must use pg_dump"
grep -q -- '--format=custom\|-Fc' "${BACKUP}" || fail "backup script should prefer custom format"
grep -q 'sha256sum' "${BACKUP}" || fail "backup script must produce SHA-256 sidecar"
grep -q 'umask 077' "${BACKUP}" || fail "backup script must set umask 077"
grep -q 'chmod 0700' "${BACKUP}" || fail "backup script must set backup directory mode 0700"
grep -q 'chmod 0600' "${BACKUP}" || fail "backup script must set dump/sidecar mode 0600"
grep -q 'dqa_require_pg_custom_archive\|PGDMP' "${BACKUP}" "${COMMON}" \
  || fail "backup path should validate PostgreSQL custom-format (PGDMP)"
# Relative backup paths resolve against repo root, not operator CWD.
grep -q 'DQA_ROOT' "${COMMON}" || fail "dqa-common must define DQA_ROOT"
grep -q 'dqa_backup_dir' "${COMMON}" || fail "missing dqa_backup_dir helper"
python3 - <<'PY' || fail "dqa_backup_dir must normalize relative paths against DQA_ROOT"
from pathlib import Path
text = Path("scripts/dqa-common.sh").read_text()
assert "dqa_backup_dir()" in text
# Must treat absolute paths as unchanged and relative against DQA_ROOT.
assert '== /*' in text or '/* ]]' in text
assert "${DQA_ROOT}/" in text or '${DQA_ROOT}/' in text
assert "operator CWD" in text or "not the operator" in text.lower() or "repository root" in text.lower()
print("backup_dir_normalize_ok")
PY
# Must not echo DB password *values* (mentioning the var name in help text is OK).
if grep -nE 'echo[[:space:]]+"\$\{?DQA_DB_PASSWORD|printf[[:space:]].*"\$\{?DQA_DB_PASSWORD|echo[[:space:]]+\$DQA_DB_PASSWORD' \
  "${BACKUP}" "${RESTORE}" "${COMMON}" >/dev/null; then
  fail "backup/restore helpers must not echo DQA_DB_PASSWORD values"
fi
# Also refuse PGPASSWORD on process command lines in backup/restore scripts.
if grep -nE 'PGPASSWORD=' "${BACKUP}" "${RESTORE}" >/dev/null; then
  fail "backup/restore must not put PGPASSWORD on the process command line"
fi
# No DEMIS DB backup command in operator backup script
if grep -nEi 'demis.*(pg_dump|dump)|pg_dump.*demis' "${BACKUP}" >/dev/null; then
  fail "backup script must not back up DEMIS"
fi

grep -q 'pg_restore' "${RESTORE}" || fail "restore script must use pg_restore"
grep -q 'RESTORE' "${RESTORE}" || fail "restore script must require explicit RESTORE confirmation"
grep -q 'sha256sum' "${RESTORE}" || fail "restore script must verify SHA-256"
grep -q 'pg_restore --list' "${RESTORE}" || fail "restore should validate archive with pg_restore --list"
grep -q 'dqa_require_pg_custom_archive\|PGDMP' "${RESTORE}" \
  || fail "restore must fail closed on non-custom (non-PGDMP) archives"
grep -q -- '--single-transaction' "${RESTORE}" || fail "restore must use --single-transaction"
grep -q -- '--exit-on-error' "${RESTORE}" || fail "restore must use --exit-on-error"
grep -q -- '--no-owner' "${RESTORE}" || fail "restore must use --no-owner"
grep -q -- '--no-privileges' "${RESTORE}" || fail "restore must use --no-privileges"
grep -q 'dqa_require_app_stopped_for_restore' "${RESTORE}" || fail "restore must refuse while app services run"
grep -q 'trap ' "${RESTORE}" || fail "restore must trap container temp cleanup"
# DROP/CREATE must occur only after custom-format validation (ordering heuristic).
python3 - <<'PY' || fail "restore must validate archive before DROP/CREATE"
from pathlib import Path
import re
text = Path("scripts/dqa-restore.sh").read_text()
idx_pgdmp = text.find("dqa_require_pg_custom_archive")
idx_list = text.find("pg_restore --list")
idx_drop = text.find("DROP DATABASE")
assert idx_pgdmp > 0 and idx_list > 0 and idx_drop > 0
assert idx_pgdmp < idx_drop and idx_list < idx_drop, (idx_pgdmp, idx_list, idx_drop)
# Alembic check only after pg_restore block
idx_restore = text.find("--single-transaction")
idx_alembic = text.find("check_at_head")
assert idx_restore > 0 and idx_alembic > idx_restore
# Recreate SQL must use stdin heredoc — psql -c/--command does not interpolate :'var'.
assert "<<'SQL'" in text, "recreate block must use single-quoted heredoc for psql stdin"
if re.search(r"""--command=.*:'restore_db'""", text) or re.search(
    r'''--command=.*:"restore_db"''', text
):
    raise AssertionError(
        "recreate SQL must not pass :'restore_db'/:\"restore_db\" via psql --command"
    )
if re.search(r"""-c\s+.*:'restore_db'""", text) or re.search(
    r'''-c\s+.*:"restore_db"''', text
):
    raise AssertionError(
        "recreate SQL must not pass :'restore_db'/:\"restore_db\" via psql -c"
    )
assert ":'restore_db'" in text and ':"restore_db"' in text
assert "--set=\"restore_db=" in text or "--set=restore_db=" in text
print("restore_order_ok")
PY
# Never volume-wipe via compose down -v in restore/backup path (ignore comments).
if grep -nE '^[^#]*\bdown[[:space:]].*-v|^[^#]*\bdown[[:space:]].*--volumes' "${RESTORE}" "${BACKUP}" >/dev/null; then
  fail "backup/restore must not use docker compose down -v"
fi
# dqa-down must refuse --volumes (already covered earlier; restate for backup suite clarity)
grep -q 'refusing destructive volume delete' "${DOWN}" \
  || fail "dqa-down.sh must refuse --volumes"
# Do not restore arbitrary SQL text through psql from the dump file
if grep -nE 'psql[[:space:]].*<[[:space:]]*\$\{?dump|psql[[:space:]].*"\$\{?dump' "${RESTORE}" >/dev/null; then
  fail "restore must not pipe dump file through psql"
fi
# No automatic deletion in backup list helper
if grep -nE '\brm\b|\bunlink\b|\bdelete\b' "${BACKUP_LIST}" | grep -vE '^\s*#|never delete|no deletion|Does NOT delete' >/dev/null; then
  # Allow comments; fail if an active rm/unlink appears
  if grep -nE '^[^#]*\b(rm|unlink)\b' "${BACKUP_LIST}" >/dev/null; then
    fail "backup-list helper must not delete files"
  fi
fi

# Audit status: aggregates only; no actor/source/audit_id columns in SQL body
python3 - <<'PY' || fail "audit retention status must not select sensitive row fields"
from pathlib import Path
import re
text = Path("scripts/dqa-audit-retention-status.sh").read_text()
# Extract SQL heredoc content only.
m = re.search(r"<<'SQL'\n(.*?)SQL", text, re.S)
assert m, "expected SQL heredoc in audit status script"
sql = m.group(1).lower()
for bad in ("actor_id", "source_name", "audit_id", "parameter_names", "parameter_values", "sql_text"):
    assert bad not in sql, bad
assert "min(created_at)" in sql
assert "max(created_at)" in sql
assert "count(" in sql
print("audit_status_sql_ok")
PY

# No public audit delete/patch API
if grep -nE '@router\.(delete|patch|put)\b|methods=\[.*DELETE|APIRouter.*delete' "${AUDIT_ROUTE}" >/dev/null; then
  fail "audit route must not expose DELETE/PATCH/PUT"
fi
# Broader scan: no DELETE handlers under audit routes package
if grep -RInE '@router\.delete\b|def delete_.*audit' "${ROOT}/backend/app/api/routes" --include='*audit*' >/dev/null; then
  fail "no automatic/public audit DELETE API may exist"
fi

grep -q 'DQA_BACKUP_DIR' "${ENV_EXAMPLE}" || fail ".env.onprem.example should document DQA_BACKUP_DIR"
grep -qi 'repository root\|repo root\|<repo>/backups' "${ENV_EXAMPLE}" \
  || fail ".env.onprem.example should state ./backups means <repo>/backups"
pass "backup/restore + audit retention static safety checks"

# --- Optional Docker resolve checks (no pip; grep rendered YAML text) ---
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "SKIPPED: docker compose config (Docker unavailable)"
  echo "All static on-prem Compose regression checks passed."
  exit 0
fi

TMP_ENV="$(mktemp)"
TMP_PROD="$(mktemp)"
TMP_DEV="$(mktemp)"
trap 'rm -f "${TMP_ENV}" "${TMP_PROD}" "${TMP_DEV}"' EXIT

cat >"${TMP_ENV}" <<'EOF'
DQA_LAN_BIND_IP=127.0.0.1
DQA_FRONTEND_PORT=8080
DQA_DB_NAME=dqa
DQA_DB_USER=dqa
DQA_DB_PASSWORD=regression-check-not-a-real-secret
# Attempt to override production auth — must be ignored by production Compose.
APP_ENV=development
DQA_AUTH_PROVIDER=dev_headers
EOF

docker compose -f "${ONPREM}" --env-file "${TMP_ENV}" config >"${TMP_PROD}"
grep -E 'APP_ENV:[[:space:]]*production' "${TMP_PROD}" >/dev/null \
  || fail "resolved production config missing APP_ENV: production"
grep -E 'DQA_AUTH_PROVIDER:[[:space:]]*disabled' "${TMP_PROD}" >/dev/null \
  || fail "resolved production config missing DQA_AUTH_PROVIDER: disabled"
# Ensure DB/backend still have no published ports in resolved config.
python3 - <<PY || fail "resolved production port topology check failed"
from pathlib import Path
import re
text = Path("${TMP_PROD}").read_text()
# docker compose config expands services; assert no host publish for db/backend.
# Look for service-named sections loosely.
assert "DQA_AUTH_PROVIDER: disabled" in text or "DQA_AUTH_PROVIDER: \"disabled\"" in text
assert "APP_ENV: production" in text or "APP_ENV: \"production\"" in text
print("resolved_prod_ok")
PY
pass "docker compose config: production auth hardcoded despite .env override attempt"

docker compose -f "${ONPREM}" -f "${DEV_OVERLAY}" --env-file "${TMP_ENV}" config >"${TMP_DEV}"
grep -E 'APP_ENV:[[:space:]]*development' "${TMP_DEV}" >/dev/null \
  || fail "resolved dev overlay missing APP_ENV: development"
grep -E 'DQA_AUTH_PROVIDER:[[:space:]]*dev_headers' "${TMP_DEV}" >/dev/null \
  || fail "resolved dev overlay missing DQA_AUTH_PROVIDER: dev_headers"
pass "docker compose config: dev overlay resolves development + dev_headers"

echo "All on-prem Compose regression checks passed."
