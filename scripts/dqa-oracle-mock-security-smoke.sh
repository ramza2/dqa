#!/usr/bin/env bash
# Development-only DQA Oracle mock security smoke test.
#
# Verifies fail-closed parameter validation, RBAC, and audit redaction.
# Does not mutate Catalog, Query Template, Connection Profile, or DEMIS data.
#
# Never use this script against production or real clinical data.
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
invalid_parameter_value = os.environ.get(
    "DQA_SMOKE_INVALID_PARAMETER_VALUE",
    "DQA TEST!",
)

operator_headers = {
    "X-DQA-Dev-Actor": "dqa-security-smoke-operator",
    "X-DQA-Dev-Roles": "query_operator",
}
viewer_headers = {
    "X-DQA-Dev-Actor": "dqa-security-smoke-viewer",
    "X-DQA-Dev-Roles": "viewer",
}
auditor_headers = {
    "X-DQA-Dev-Actor": "dqa-security-smoke-auditor",
    "X-DQA-Dev-Roles": "auditor",
}


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def make_request(
    path: str,
    *,
    headers: dict[str, str],
    payload: dict | None = None,
) -> urllib.request.Request:
    data = None
    method = "GET"
    request_headers = dict(headers)

    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        method = "POST"
        request_headers["Content-Type"] = "application/json"

    return urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        headers=request_headers,
        method=method,
    )


def request_json(
    path: str,
    *,
    headers: dict[str, str],
    payload: dict | None = None,
) -> dict:
    req = make_request(path, headers=headers, payload=payload)

    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        fail(f"{req.method} {path} returned HTTP {exc.code}: {body[:500]}")
    except Exception as exc:
        fail(f"{req.method} {path} failed: {type(exc).__name__}: {exc}")

    try:
        parsed = json.loads(raw)
    except Exception:
        fail(f"{req.method} {path} returned invalid JSON")

    if not isinstance(parsed, dict):
        fail(f"{req.method} {path} returned non-object JSON")
    return parsed


def expect_error(
    path: str,
    *,
    headers: dict[str, str],
    payload: dict | None,
    expected_status: int,
    expected_code: str,
    forbidden_value: str | None = None,
) -> None:
    req = make_request(path, headers=headers, payload=payload)

    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            body = response.read().decode("utf-8", errors="replace")
            fail(
                f"{req.method} {path} unexpectedly returned "
                f"HTTP {response.status}: {body[:300]}"
            )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")

        if exc.code != expected_status:
            fail(
                f"{req.method} {path} expected HTTP {expected_status}, "
                f"got {exc.code}: {body[:500]}"
            )

        try:
            parsed = json.loads(body)
        except Exception:
            fail(f"{req.method} {path} error response was not JSON")

        detail = parsed.get("detail") if isinstance(parsed, dict) else None
        code = detail.get("code") if isinstance(detail, dict) else None
        if code != expected_code:
            fail(
                f"{req.method} {path} expected code {expected_code}, "
                f"got {code!r}"
            )

        if forbidden_value and forbidden_value in body:
            fail(f"{req.method} {path} leaked rejected parameter value")

        print(
            f"PASS: {req.method} {path} "
            f"HTTP {expected_status} {expected_code}"
        )
        return
    except Exception as exc:
        fail(f"{req.method} {path} failed: {type(exc).__name__}: {exc}")

    fail(f"{req.method} {path} did not fail as expected")


recommendation = request_json(
    "/api/v1/query-recommendations",
    headers=operator_headers,
    payload={
        "source_name": source_name,
        "request_text": request_text,
    },
)

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

print(
    f"PASS: resolved security-smoke target template_id={template_id} "
    f"version_id={version_id}"
)

base_execution_payload = {
    "source_name": source_name,
    "environment": environment,
    "template_id": template_id,
    "version_id": version_id,
}

valid_execution_payload = {
    **base_execution_payload,
    "parameters": {parameter_name: parameter_value},
}

expect_error(
    "/api/v1/query-executions/execute",
    headers=operator_headers,
    payload={
        **base_execution_payload,
        "parameters": {},
    },
    expected_status=422,
    expected_code="PARAMETER_INVALID",
)

expect_error(
    "/api/v1/query-executions/preview",
    headers=operator_headers,
    payload={
        **base_execution_payload,
        "parameters": {parameter_name: invalid_parameter_value},
    },
    expected_status=422,
    expected_code="PARAMETER_INVALID",
    forbidden_value=invalid_parameter_value,
)

undeclared_value = "SHOULD_NOT_APPEAR"
expect_error(
    "/api/v1/query-executions/execute",
    headers=operator_headers,
    payload={
        **base_execution_payload,
        "parameters": {
            parameter_name: parameter_value,
            "extra_param": undeclared_value,
        },
    },
    expected_status=422,
    expected_code="PARAMETER_UNDECLARED",
    forbidden_value=undeclared_value,
)

expect_error(
    "/api/v1/query-executions/execute",
    headers=viewer_headers,
    payload=valid_execution_payload,
    expected_status=403,
    expected_code="AUTHORIZATION_DENIED",
)

execution = request_json(
    "/api/v1/query-executions/execute",
    headers=operator_headers,
    payload=valid_execution_payload,
)

audit_id = execution.get("audit_id")
if not isinstance(audit_id, str) or not audit_id:
    fail("successful execution did not return audit_id")

print(
    "PASS: operator read-only execution produced audit_id "
    f"(row_count={execution.get('row_count')})"
)

audit_path = (
    "/api/v1/audit-events/"
    + urllib.parse.quote(audit_id, safe="")
)

expect_error(
    audit_path,
    headers=viewer_headers,
    payload=None,
    expected_status=403,
    expected_code="AUTHORIZATION_DENIED",
)

audit = request_json(
    audit_path,
    headers=auditor_headers,
)

items = audit.get("items")
if not isinstance(items, list) or not items:
    fail("auditor response does not contain audit items")

serialized = json.dumps(audit, ensure_ascii=False)
if parameter_value in serialized:
    fail("audit response leaked actual parameter value")

for item in items:
    if not isinstance(item, dict):
        continue
    if item.get("parameter_logging_policy") != "NAMES_ONLY":
        fail("audit parameter logging policy is not NAMES_ONLY")

print("PASS: audit contains parameter names only; actual value not present")
print("PASS: Oracle mock DQA security smoke test")
PY
