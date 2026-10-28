#!/usr/bin/env bash
# M4-A development smoke: LLM-free approved-template execution path.
#
# Flow:
#   manual-templates → form → preview → execute → audit
#
# Never calls /query-recommendations or /query-parameters/extract.
# Never prints credentials or result row payloads.
#
# Oracle Mock readiness:
#   - Missing/unreachable mock → exit 2 with M4A_ORACLE_MOCK_BLOCKED (not PASS)
#   - Connected mock → full SELECT + durable audit checks
#
# Existing scripts/dqa-oracle-mock-smoke.sh (LLM path) remains unchanged.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=dqa-common.sh
source "${ROOT}/scripts/dqa-common.sh"

dqa_require_cmd python3
if [[ ! -f "${DQA_ENV_FILE}" ]]; then
  echo "M4A_ORACLE_MOCK_BLOCKED: missing ${DQA_ENV_FILE} (live stack smoke not runnable)" >&2
  exit 2
fi
dqa_require_env_file

bind_ip="$(dqa_env_value DQA_LAN_BIND_IP 127.0.0.1)"
frontend_port="$(dqa_env_value DQA_FRONTEND_PORT 8080)"
base_url="${DQA_SMOKE_BASE_URL:-http://${bind_ip}:${frontend_port}}"

export DQA_SMOKE_BASE_URL="${base_url}"
export DQA_M4A_REQUIRE_ORACLE_MOCK="${DQA_M4A_REQUIRE_ORACLE_MOCK:-1}"

python3 - <<'PY'
import json
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

base_url = os.environ["DQA_SMOKE_BASE_URL"].rstrip("/")
source_name = os.environ.get("DQA_SMOKE_SOURCE", "oracle_demis_mock")
environment = os.environ.get("DQA_SMOKE_ENVIRONMENT", "development")
expected_stable_key = os.environ.get(
    "DQA_SMOKE_EXPECTED_STABLE_KEY", "demis.code-master.by-group"
)
parameter_name = os.environ.get("DQA_SMOKE_PARAMETER_NAME", "cd_grp_id")
parameter_value = os.environ.get("DQA_SMOKE_PARAMETER_VALUE", "DQA_TEST")
expected_row_count = int(os.environ.get("DQA_SMOKE_EXPECTED_ROW_COUNT", "3"))
mock_host = os.environ.get("DQA_M4A_ORACLE_MOCK_HOST", "demis-oracle-test")
mock_port = int(os.environ.get("DQA_M4A_ORACLE_MOCK_PORT", "1521"))
require_mock = os.environ.get("DQA_M4A_REQUIRE_ORACLE_MOCK", "1") == "1"

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
        body = exc.read().decode("utf-8", errors="replace")
        fail(f"{verb} {path} returned HTTP {exc.code}: {body[:500]}")
    except Exception as exc:
        fail(f"{verb} {path} failed: {type(exc).__name__}: {exc}")
    try:
        parsed = json.loads(raw)
    except Exception:
        fail(f"{verb} {path} returned invalid JSON")
    if not isinstance(parsed, dict):
        fail(f"{verb} {path} returned non-object JSON")
    return parsed


def oracle_mock_ready() -> tuple[bool, str]:
    secret = os.environ.get("DEMIS_SECRET_ORACLE_PASSWORD", "").strip()
    if not secret:
        return False, "DEMIS_SECRET_ORACLE_PASSWORD is unset"
    try:
        with socket.create_connection((mock_host, mock_port), timeout=3):
            return True, "tcp ok"
    except OSError as exc:
        return False, f"tcp {mock_host}:{mock_port} unreachable ({exc.__class__.__name__})"


ready, reason = oracle_mock_ready()
if not ready:
    if require_mock:
        blocked(reason)
    print(f"M4A_ORACLE_MOCK_SKIPPED: {reason}")
    raise SystemExit(2)

print(f"PASS: oracle mock readiness ({reason})")

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
    fail(f"manual-templates missing stable_key={expected_stable_key!r}")

template_id = chosen.get("template_id")
version_id = chosen.get("version_id")
if not isinstance(template_id, int) or not isinstance(version_id, int):
    fail("manual template missing template_id/version_id")
if parameter_name not in (chosen.get("parameter_names") or []):
    fail(f"manual template does not declare {parameter_name}")
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
if form.get("template", {}).get("id") != template_id:
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
    fail(f"preview unavailable: {preview.get('execution_blockers')!r}")
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
    fail(f"unexpected row_count: expected={expected_row_count}, actual={row_count!r}")
if execution.get("truncated") is not False:
    fail("result unexpectedly truncated")
audit_id = execution.get("audit_id")
if not isinstance(audit_id, str) or not audit_id:
    fail("execution did not return audit_id")
# Never dump rows.
if "rows" in execution and isinstance(execution["rows"], list):
    print(f"PASS: read-only execution row_count={row_count} (rows omitted)")
else:
    print(f"PASS: read-only execution row_count={row_count}")

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
    fail(f"audit lifecycle incomplete: missing={sorted(missing)!r}")
for item in items:
    if isinstance(item, dict) and item.get("parameter_logging_policy") != "NAMES_ONLY":
        fail("audit parameter logging policy is not NAMES_ONLY")
serialized = json.dumps(audit, ensure_ascii=False)
if parameter_value in serialized:
    fail("audit response leaked a parameter value")
print(f"PASS: durable audit lifecycle audit_id={audit_id}")
print("PASS: M4-A LLM-free Oracle mock smoke")
PY
