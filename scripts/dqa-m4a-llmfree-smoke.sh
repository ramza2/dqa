#!/usr/bin/env bash
# M4-A development smoke: LLM-free approved-template execution path.
#
# Flow:
#   manual-templates → form → preview → execute → audit
#
# Never calls /query-recommendations or /query-parameters/extract.
# Never prints credentials, HTTP bodies, or result row payloads.
#
# Live Oracle Mock gates (all required; otherwise BLOCKED, never PASS):
#   - DQA_M4A_ALLOW_LIVE_ORACLE_MOCK=1 (explicit operator opt-in)
#   - allowlisted host demis-oracle-test:1521 only
#   - source oracle_demis_mock, environment development
#   - running Compose backend APP_ENV + DQA_AUTH_PROVIDER inspected (no defaults;
#     shell DQA_M4A_APP_ENV / DQA_M4A_AUTH_PROVIDER overrides are not proof)
#   - base URL only from env-file DQA_LAN_BIND_IP + DQA_FRONTEND_PORT;
#     arbitrary DQA_SMOKE_BASE_URL is rejected unless it exactly matches
#   - DEMIS_SECRET_ORACLE_PASSWORD present (value never printed)
# If the development Mock stack cannot be verified → exit 2 (no LIVE_E2E PASS).
#
# Existing scripts/dqa-oracle-mock-smoke.sh (LLM path) remains unchanged.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=dqa-common.sh
source "${ROOT}/scripts/dqa-common.sh"

ALLOWED_MOCK_HOST="demis-oracle-test"
ALLOWED_MOCK_PORT="1521"
ALLOWED_SOURCE="oracle_demis_mock"
ALLOWED_ENVIRONMENT="development"

dqa_require_cmd python3

if [[ "${DQA_M4A_ALLOW_LIVE_ORACLE_MOCK:-}" != "1" ]]; then
  echo "M4A_ORACLE_MOCK_BLOCKED: set DQA_M4A_ALLOW_LIVE_ORACLE_MOCK=1 for explicit live Mock smoke" >&2
  exit 2
fi

if [[ -n "${DQA_M4A_APP_ENV:-}" || -n "${DQA_M4A_AUTH_PROVIDER:-}" ]]; then
  echo "M4A_ORACLE_MOCK_BLOCKED: DQA_M4A_APP_ENV/DQA_M4A_AUTH_PROVIDER overrides are not accepted as environment proof" >&2
  exit 2
fi

if [[ ! -f "${DQA_ENV_FILE}" ]]; then
  echo "M4A_ORACLE_MOCK_BLOCKED: missing env file for live stack smoke" >&2
  exit 2
fi
dqa_require_env_file

# LAN frontend entry must be explicit in the env file (no silent defaults).
bind_ip="$(dqa_env_value DQA_LAN_BIND_IP "")"
frontend_port="$(dqa_env_value DQA_FRONTEND_PORT "")"
if [[ -z "$bind_ip" || -z "$frontend_port" ]]; then
  echo "M4A_ORACLE_MOCK_BLOCKED: DQA_LAN_BIND_IP/DQA_FRONTEND_PORT missing from env file" >&2
  exit 2
fi
if [[ ! "$bind_ip" =~ ^[0-9A-Fa-f.:]+$ && ! "$bind_ip" =~ ^[A-Za-z0-9.-]+$ ]]; then
  echo "M4A_ORACLE_MOCK_BLOCKED: DQA_LAN_BIND_IP failed safe validation" >&2
  exit 2
fi
if [[ ! "$frontend_port" =~ ^[0-9]+$ ]] || (( frontend_port < 1 || frontend_port > 65535 )); then
  echo "M4A_ORACLE_MOCK_BLOCKED: DQA_FRONTEND_PORT failed numeric validation" >&2
  exit 2
fi

derived_base_url="http://${bind_ip}:${frontend_port}"
if [[ -n "${DQA_SMOKE_BASE_URL:-}" ]]; then
  requested="${DQA_SMOKE_BASE_URL%/}"
  if [[ "$requested" != "$derived_base_url" ]]; then
    echo "M4A_ORACLE_MOCK_BLOCKED: DQA_SMOKE_BASE_URL must exactly match env-file LAN frontend URL" >&2
    exit 2
  fi
fi
base_url="$derived_base_url"

MOCK_HOST="${DQA_M4A_ORACLE_MOCK_HOST:-$ALLOWED_MOCK_HOST}"
MOCK_PORT="${DQA_M4A_ORACLE_MOCK_PORT:-$ALLOWED_MOCK_PORT}"
SOURCE_NAME="${DQA_SMOKE_SOURCE:-$ALLOWED_SOURCE}"
ENVIRONMENT="${DQA_SMOKE_ENVIRONMENT:-$ALLOWED_ENVIRONMENT}"

if [[ ! "$MOCK_HOST" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo "M4A_ORACLE_MOCK_BLOCKED: mock host failed safe-charset validation" >&2
  exit 2
fi
if [[ ! "$MOCK_PORT" =~ ^[0-9]+$ ]] || (( MOCK_PORT < 1 || MOCK_PORT > 65535 )); then
  echo "M4A_ORACLE_MOCK_BLOCKED: mock port failed numeric validation" >&2
  exit 2
fi
if [[ "$MOCK_HOST" != "$ALLOWED_MOCK_HOST" || "$MOCK_PORT" != "$ALLOWED_MOCK_PORT" ]]; then
  echo "M4A_ORACLE_MOCK_BLOCKED: host/port is not the allowlisted Oracle Mock endpoint" >&2
  exit 2
fi
if [[ "$SOURCE_NAME" != "$ALLOWED_SOURCE" ]]; then
  echo "M4A_ORACLE_MOCK_BLOCKED: source_name is not the allowlisted oracle_demis_mock" >&2
  exit 2
fi
if [[ "$ENVIRONMENT" != "$ALLOWED_ENVIRONMENT" ]]; then
  echo "M4A_ORACLE_MOCK_BLOCKED: environment is not development" >&2
  exit 2
fi

# Verify the *running* Compose backend — never invent APP_ENV/AUTH defaults.
if ! command -v docker >/dev/null 2>&1; then
  echo "M4A_ORACLE_MOCK_BLOCKED: docker required to verify running development Mock stack" >&2
  exit 2
fi
if ! docker info >/dev/null 2>&1; then
  echo "M4A_ORACLE_MOCK_BLOCKED: docker daemon unavailable; cannot verify development Mock stack" >&2
  exit 2
fi

mapfile -t backend_cids < <(
  docker ps -q \
    --filter "label=com.docker.compose.project=${DQA_COMPOSE_PROJECT_NAME}" \
    --filter "label=com.docker.compose.service=backend" 2>/dev/null || true
)
if [[ "${#backend_cids[@]}" -ne 1 || -z "${backend_cids[0]:-}" ]]; then
  echo "M4A_ORACLE_MOCK_BLOCKED: expected exactly one running Compose backend for project ${DQA_COMPOSE_PROJECT_NAME}" >&2
  exit 2
fi
backend_cid="${backend_cids[0]}"

# Read only the two required keys from the container env; never dump full env/secrets.
app_env="$(
  docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$backend_cid" \
    | awk -F= '$1=="APP_ENV" { print substr($0, index($0, "=")+1); exit }'
)"
auth_provider="$(
  docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$backend_cid" \
    | awk -F= '$1=="DQA_AUTH_PROVIDER" { print substr($0, index($0, "=")+1); exit }'
)"
if [[ -z "$app_env" ]]; then
  echo "M4A_ORACLE_MOCK_BLOCKED: running backend APP_ENV is missing" >&2
  exit 2
fi
if [[ -z "$auth_provider" ]]; then
  echo "M4A_ORACLE_MOCK_BLOCKED: running backend DQA_AUTH_PROVIDER is missing" >&2
  exit 2
fi
if [[ "$app_env" != "development" && "$app_env" != "test" ]]; then
  echo "M4A_ORACLE_MOCK_BLOCKED: running backend APP_ENV is not development|test" >&2
  exit 2
fi
if [[ "$auth_provider" != "dev_headers" ]]; then
  echo "M4A_ORACLE_MOCK_BLOCKED: running backend DQA_AUTH_PROVIDER is not dev_headers" >&2
  exit 2
fi

# Confirm frontend publishes the same LAN entry used as the smoke base URL.
mapfile -t frontend_cids < <(
  docker ps -q \
    --filter "label=com.docker.compose.project=${DQA_COMPOSE_PROJECT_NAME}" \
    --filter "label=com.docker.compose.service=frontend" 2>/dev/null || true
)
if [[ "${#frontend_cids[@]}" -ne 1 || -z "${frontend_cids[0]:-}" ]]; then
  echo "M4A_ORACLE_MOCK_BLOCKED: expected exactly one running Compose frontend for project ${DQA_COMPOSE_PROJECT_NAME}" >&2
  exit 2
fi
frontend_cid="${frontend_cids[0]}"
export DQA_M4A_FRONTEND_CID="$frontend_cid"
export DQA_M4A_EXPECTED_BIND_IP="$bind_ip"
export DQA_M4A_EXPECTED_FRONTEND_PORT="$frontend_port"
if ! python3 - <<'PY'
import json
import os
import subprocess
import sys

cid = os.environ["DQA_M4A_FRONTEND_CID"]
bind_ip = os.environ["DQA_M4A_EXPECTED_BIND_IP"]
port = os.environ["DQA_M4A_EXPECTED_FRONTEND_PORT"]
try:
    raw = subprocess.check_output(
        ["docker", "inspect", cid],
        stderr=subprocess.DEVNULL,
        timeout=15,
    )
except (OSError, subprocess.SubprocessError):
    print("frontend inspect failed", file=sys.stderr)
    raise SystemExit(1)
data = json.loads(raw)
if not isinstance(data, list) or len(data) != 1:
    print("unexpected inspect payload", file=sys.stderr)
    raise SystemExit(1)
ports = (data[0].get("NetworkSettings") or {}).get("Ports") or {}
bindings = ports.get("80/tcp") or ports.get("80") or []
if not isinstance(bindings, list) or not bindings:
    print("frontend has no host binding for container port 80", file=sys.stderr)
    raise SystemExit(1)
matched = False
for item in bindings:
    if not isinstance(item, dict):
        continue
    host_ip = str(item.get("HostIp") or "")
    host_port = str(item.get("HostPort") or "")
    if host_port != port:
        continue
    # Exact LAN bind, or wildcard publish only when operator bind is loopback.
    if host_ip in {"", "0.0.0.0", "::"} and bind_ip in {"127.0.0.1", "::1"}:
        matched = True
        break
    if host_ip == bind_ip:
        matched = True
        break
if not matched:
    print("frontend publish does not match env-file LAN bind/port", file=sys.stderr)
    raise SystemExit(1)
PY
then
  echo "M4A_ORACLE_MOCK_BLOCKED: running frontend publish does not match env-file LAN entry" >&2
  exit 2
fi

export DQA_SMOKE_BASE_URL="$base_url"
export DQA_M4A_ORACLE_MOCK_HOST="$MOCK_HOST"
export DQA_M4A_ORACLE_MOCK_PORT="$MOCK_PORT"
export DQA_SMOKE_SOURCE="$SOURCE_NAME"
export DQA_SMOKE_ENVIRONMENT="$ENVIRONMENT"
export DQA_M4A_APP_ENV="$app_env"
export DQA_M4A_AUTH_PROVIDER="$auth_provider"
export DQA_M4A_DERIVED_BASE_URL="$derived_base_url"

# Run the credential and TCP preflight in the verified backend container:
# Docker service DNS (demis-oracle-test) is intentionally not host-resolvable.
# Never disclose credential values, probe output, or Oracle response payloads.
if ! docker exec -i "$backend_cid" python - <<'PY' >/dev/null 2>&1
import os
import socket

if not os.environ.get("DEMIS_SECRET_ORACLE_PASSWORD", "").strip():
    raise SystemExit(2)
try:
    with socket.create_connection(("demis-oracle-test", 1521), timeout=3):
        pass
except OSError:
    raise SystemExit(3)
PY
then
  echo "M4A_ORACLE_MOCK_BLOCKED: verified backend credential or Oracle Mock TCP preflight failed" >&2
  exit 2
fi

python3 - <<'PY'
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ALLOWED_HOST = "demis-oracle-test"
ALLOWED_PORT = 1521
ALLOWED_SOURCE = "oracle_demis_mock"
ALLOWED_ENVIRONMENT = "development"

base_url = os.environ["DQA_SMOKE_BASE_URL"].rstrip("/")
derived_base_url = os.environ.get("DQA_M4A_DERIVED_BASE_URL", "").rstrip("/")
source_name = os.environ["DQA_SMOKE_SOURCE"]
environment = os.environ["DQA_SMOKE_ENVIRONMENT"]
expected_stable_key = os.environ.get(
    "DQA_SMOKE_EXPECTED_STABLE_KEY", "demis.code-master.by-group"
)
parameter_name = os.environ.get("DQA_SMOKE_PARAMETER_NAME", "cd_grp_id")
parameter_value = os.environ.get("DQA_SMOKE_PARAMETER_VALUE", "DQA_TEST")
expected_row_count = int(os.environ.get("DQA_SMOKE_EXPECTED_ROW_COUNT", "3"))
mock_host = os.environ["DQA_M4A_ORACLE_MOCK_HOST"]
mock_port = int(os.environ["DQA_M4A_ORACLE_MOCK_PORT"])
# Values must be exported from the verified running backend — never invent defaults.
app_env = os.environ.get("DQA_M4A_APP_ENV", "")
auth_provider = os.environ.get("DQA_M4A_AUTH_PROVIDER", "")

operator_headers = {
    "X-DQA-Dev-Actor": "dqa-m4a-operator",
    "X-DQA-Dev-Roles": "query_operator",
}
auditor_headers = {
    "X-DQA-Dev-Actor": "dqa-m4a-auditor",
    "X-DQA-Dev-Roles": "auditor",
}


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def blocked(message: str) -> None:
    print(f"M4A_ORACLE_MOCK_BLOCKED: {message}", file=sys.stderr)
    raise SystemExit(2)


def assert_live_allowlist() -> None:
    if not app_env:
        blocked("APP_ENV missing after running-stack verification")
    if app_env not in {"development", "test"}:
        blocked("APP_ENV not development|test")
    if not auth_provider:
        blocked("DQA_AUTH_PROVIDER missing after running-stack verification")
    if auth_provider != "dev_headers":
        blocked("auth provider is not dev_headers")
    if mock_host != ALLOWED_HOST or mock_port != ALLOWED_PORT:
        blocked("mock endpoint is not allowlisted")
    if source_name != ALLOWED_SOURCE:
        blocked("source_name is not allowlisted oracle_demis_mock")
    if environment != ALLOWED_ENVIRONMENT:
        blocked("environment is not development")
    if not derived_base_url.startswith("http://"):
        blocked("derived LAN base URL is invalid")
    if base_url != derived_base_url:
        blocked("smoke base URL does not match verified LAN frontend entry")
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme != "http" or not parsed.netloc or parsed.path not in {"", "/"}:
        blocked("smoke base URL must be bare http://bind:port LAN entry")


def request_json(
    path: str,
    *,
    headers: dict[str, str],
    payload: dict | None = None,
    method: str | None = None,
) -> dict:
    url = f"{base_url}{path}"
    data = None
    request_headers = dict(headers)
    verb = method or ("POST" if payload is not None else "GET")
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=request_headers, method=verb)
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        # Never echo response bodies (may contain rows/secrets).
        _ = exc.read()
        fail(f"{verb} {path} returned HTTP {exc.code}")
    except Exception as exc:
        fail(f"{verb} {path} failed: {type(exc).__name__}")
    try:
        parsed = json.loads(raw)
    except Exception:
        fail(f"{verb} {path} returned invalid JSON")
    if not isinstance(parsed, dict):
        fail(f"{verb} {path} returned non-object JSON")
    return parsed


assert_live_allowlist()
# The fail-closed backend-container preflight already verified secret + TCP.
print("M4A_ORACLE_MOCK_REACHABLE: allowlisted mock TCP ok (verified backend)")
print("LIVE_E2E=RUNNING")

manual = request_json(
    "/api/v1/query-executions/manual-templates?"
    + urllib.parse.urlencode({"source_name": source_name, "limit": 100, "offset": 0}),
    headers=operator_headers,
)
items = manual.get("items")
if not isinstance(items, list) or not items:
    fail("manual-templates returned no eligible templates")
chosen = next(
    (
        item
        for item in items
        if isinstance(item, dict) and item.get("stable_key") == expected_stable_key
    ),
    None,
)
if chosen is None:
    fail("manual-templates missing expected stable_key")

template_id = chosen.get("template_id")
version_id = chosen.get("version_id")
if not isinstance(template_id, int) or not isinstance(version_id, int):
    fail("manual template missing template_id/version_id")
if parameter_name not in (chosen.get("parameter_names") or []):
    fail("manual template missing expected parameter name")
print(f"PASS: manual-templates template_id={template_id} version_id={version_id}")

form = request_json(
    "/api/v1/query-executions/form?"
    + urllib.parse.urlencode(
        {
            "source_name": source_name,
            "template_id": template_id,
            "version_id": version_id,
        }
    ),
    headers=operator_headers,
)
if form.get("template", {}).get("template_id") != template_id:
    fail("form template_id mismatch")
print("PASS: execution form metadata")

execution_payload = {
    "source_name": source_name,
    "environment": environment,
    "template_id": template_id,
    "version_id": version_id,
    "parameters": {parameter_name: parameter_value},
}

preview = request_json(
    "/api/v1/query-executions/preview",
    headers=operator_headers,
    payload=execution_payload,
)
if preview.get("execution_available") is not True:
    fail("preview unavailable")
if (preview.get("resolved_parameters") or {}).get(parameter_name) != parameter_value:
    fail("preview resolved parameters mismatch")
print("PASS: execution preview available")

execution = request_json(
    "/api/v1/query-executions/execute",
    headers=operator_headers,
    payload=execution_payload,
)
row_count = execution.get("row_count")
if row_count != expected_row_count:
    fail("unexpected row_count")
if execution.get("truncated") is not False:
    fail("result unexpectedly truncated")
audit_id = execution.get("audit_id")
if not isinstance(audit_id, str) or not audit_id:
    fail("execution did not return audit_id")
print(f"PASS: read-only execution row_count={row_count} (rows omitted)")

audit = request_json(
    f"/api/v1/audit-events/{urllib.parse.quote(audit_id, safe='')}",
    headers=auditor_headers,
)
items = audit.get("items")
if not isinstance(items, list):
    fail("audit response missing items")
actual = {
    (item.get("event_type"), item.get("status"))
    for item in items
    if isinstance(item, dict)
}
required = {
    ("QUERY_REQUEST", "STARTED"),
    ("QUERY_REQUEST", "SUCCEEDED"),
    ("QUERY_EXECUTION", "STARTED"),
    ("QUERY_EXECUTION", "SUCCEEDED"),
}
missing = required - actual
if missing:
    fail("audit lifecycle incomplete")
for item in items:
    if isinstance(item, dict) and item.get("parameter_logging_policy") != "NAMES_ONLY":
        fail("audit parameter logging policy is not NAMES_ONLY")
serialized = json.dumps(audit, ensure_ascii=False)
if parameter_value in serialized:
    fail("audit response leaked a parameter value")
print("PASS: durable audit lifecycle (audit_id omitted from stdout)")
print("LIVE_E2E=PASS")
print("PASS: M4-A LLM-free Oracle mock live smoke")
PY
