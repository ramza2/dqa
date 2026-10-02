#!/usr/bin/env bash
# Development-only DQA Oracle mock end-to-end smoke test.
#
# Verifies:
#   recommendation -> parameter extraction -> preview -> execute -> audit
#
# Never use this script against production or real clinical data.
# It does not print query result rows or credentials.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=dqa-common.sh
source "${ROOT}/scripts/dqa-common.sh"

dqa_require_cmd python3
dqa_require_env_file

bind_ip="$(dqa_env_value DQA_LAN_BIND_IP 127.0.0.1)"
frontend_port="$(dqa_env_value DQA_FRONTEND_PORT 8080)"

base_url="${DQA_SMOKE_BASE_URL:-http://${bind_ip}:${frontend_port}}"

DQA_SMOKE_BASE_URL="${base_url}" python3 - <<'PY'
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

base_url = os.environ["DQA_SMOKE_BASE_URL"].rstrip("/")

source_name = os.environ.get("DQA_SMOKE_SOURCE", "oracle_demis_mock")
environment = os.environ.get("DQA_SMOKE_ENVIRONMENT", "development")
request_text = os.environ.get(
    "DQA_SMOKE_REQUEST_TEXT",
    "DQA_TEST 그룹의 코드만 보여줘",
)
expected_stable_key = os.environ.get(
    "DQA_SMOKE_EXPECTED_STABLE_KEY",
    "demis.code-master.by-group",
)
parameter_name = os.environ.get("DQA_SMOKE_PARAMETER_NAME", "cd_grp_id")
parameter_value = os.environ.get("DQA_SMOKE_PARAMETER_VALUE", "DQA_TEST")
expected_row_count = int(os.environ.get("DQA_SMOKE_EXPECTED_ROW_COUNT", "3"))

operator_headers = {
    "X-DQA-Dev-Actor": "dqa-smoke-operator",
    "X-DQA-Dev-Roles": "query_operator",
}
auditor_headers = {
    "X-DQA-Dev-Actor": "dqa-smoke-auditor",
    "X-DQA-Dev-Roles": "auditor",
}


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def request_json(
    path: str,
    *,
    headers: dict[str, str],
    payload: dict | None = None,
) -> dict:
    url = f"{base_url}{path}"
    data = None
    method = "GET"

    request_headers = dict(headers)
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        method = "POST"
        request_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        url,
        data=data,
        headers=request_headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        fail(f"{method} {path} returned HTTP {exc.code}: {body[:500]}")
    except Exception as exc:
        fail(f"{method} {path} failed: {type(exc).__name__}: {exc}")

    try:
        parsed = json.loads(raw)
    except Exception:
        fail(f"{method} {path} returned invalid JSON")

    if not isinstance(parsed, dict):
        fail(f"{method} {path} returned non-object JSON")
    return parsed


recommendation = request_json(
    "/api/v1/query-recommendations",
    headers=operator_headers,
    payload={
        "source_name": source_name,
        "request_text": request_text,
    },
)

if recommendation.get("needs_clarification"):
    fail("recommendation unexpectedly requires clarification")

recommended = recommendation.get("recommended_template") or {}
if recommended.get("stable_key") != expected_stable_key:
    fail(
        "unexpected recommended template: "
        f"{recommended.get('stable_key')!r}"
    )

template_id = recommended.get("template_id")
version_id = recommended.get("version_id")
if not isinstance(template_id, int) or not isinstance(version_id, int):
    fail("recommendation did not return template_id/version_id")

if parameter_name not in (recommended.get("parameter_names") or []):
    fail(f"recommended template does not declare {parameter_name}")

print(
    f"PASS: recommendation template_id={template_id} "
    f"version_id={version_id}"
)

extraction = request_json(
    "/api/v1/query-parameters/extract",
    headers=operator_headers,
    payload={
        "source_name": source_name,
        "template_id": template_id,
        "version_id": version_id,
        "request_text": request_text,
    },
)

if extraction.get("needs_clarification"):
    fail("parameter extraction unexpectedly requires clarification")

resolved = extraction.get("resolved_parameters") or {}
if resolved.get(parameter_name) != parameter_value:
    fail(f"unexpected resolved value for {parameter_name}")

print(f"PASS: parameter extraction resolved {parameter_name}")

execution_payload = {
    "source_name": source_name,
    "environment": environment,
    "template_id": template_id,
    "version_id": version_id,
    "parameters": {
        parameter_name: parameter_value,
    },
}

preview = request_json(
    "/api/v1/query-executions/preview",
    headers=operator_headers,
    payload=execution_payload,
)

if preview.get("execution_available") is not True:
    fail(
        "execution preview unavailable: "
        f"{preview.get('execution_blockers')!r}"
    )

preview_params = preview.get("resolved_parameters") or {}
if preview_params.get(parameter_name) != parameter_value:
    fail("preview resolved parameters differ from extracted parameters")

print("PASS: execution preview available")

execution = request_json(
    "/api/v1/query-executions/execute",
    headers=operator_headers,
    payload=execution_payload,
)

row_count = execution.get("row_count")
if row_count != expected_row_count:
    fail(
        f"unexpected row_count: expected={expected_row_count}, "
        f"actual={row_count!r}"
    )

if execution.get("truncated") is not False:
    fail("smoke result was unexpectedly truncated")

audit_id = execution.get("audit_id")
if not isinstance(audit_id, str) or not audit_id:
    fail("execution did not return audit_id")

print(
    f"PASS: read-only execution row_count={row_count} "
    f"elapsed_ms={execution.get('elapsed_ms')}"
)

audit = request_json(
    f"/api/v1/audit-events/{urllib.parse.quote(audit_id, safe='')}",
    headers=auditor_headers,
)

items = audit.get("items")
if not isinstance(items, list):
    fail("audit response does not contain items")

actual_events = {
    (item.get("event_type"), item.get("status"))
    for item in items
    if isinstance(item, dict)
}
required_events = {
    ("QUERY_REQUEST", "STARTED"),
    ("QUERY_REQUEST", "SUCCEEDED"),
    ("QUERY_EXECUTION", "STARTED"),
    ("QUERY_EXECUTION", "SUCCEEDED"),
}
missing = required_events - actual_events
if missing:
    fail(f"audit lifecycle is incomplete: missing={sorted(missing)!r}")

for item in items:
    if not isinstance(item, dict):
        continue
    if item.get("parameter_logging_policy") != "NAMES_ONLY":
        fail("audit parameter logging policy is not NAMES_ONLY")

audit_serialized = json.dumps(audit, ensure_ascii=False)
if parameter_value in audit_serialized:
    fail("audit response leaked a parameter value")

print(f"PASS: audit lifecycle complete audit_id={audit_id}")
print("PASS: Oracle mock DQA E2E smoke test")
PY
