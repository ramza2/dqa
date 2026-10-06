#!/usr/bin/env bash
# Development-only DQA metadata bootstrap for the Oracle mock environment.
#
# Creates/validates:
#   - development Connection Profile for oracle_demis_mock
#   - approved/enabled demis.code-master.by-group Query Template
#
# Preconditions:
#   - development dev_headers auth is enabled
#   - oracle_demis_mock has an active Catalog revision
#   - DEMIS_SECRET_ORACLE_PASSWORD is supplied to the backend runtime
#
# This script never writes to DEMIS/Oracle data and never prints credentials.
# Never use against production or real clinical data.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=dqa-common.sh
source "${ROOT}/scripts/dqa-common.sh"

dqa_require_cmd python3
dqa_require_env_file

bind_ip="$(dqa_env_value DQA_LAN_BIND_IP 127.0.0.1)"
frontend_port="$(dqa_env_value DQA_FRONTEND_PORT 8080)"
base_url="${DQA_SMOKE_BASE_URL:-http://${bind_ip}:${frontend_port}}"

DQA_BOOTSTRAP_BASE_URL="${base_url}" python3 - <<'PY'
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

base_url = os.environ["DQA_BOOTSTRAP_BASE_URL"].rstrip("/")

SOURCE = "oracle_demis_mock"
ENVIRONMENT = "development"

PROFILE = {
    "name": "DEMIS Oracle Mock - Development",
    "source_name": SOURCE,
    "environment": ENVIRONMENT,
    "dbms_type": "oracle",
    "host": "demis-oracle-test",
    "port": 1521,
    "database_name": "FREEPDB1",
    "username": "DEMIS_RO",
    "credential_secret_ref": "env:DEMIS_SECRET_ORACLE_PASSWORD",
}

STABLE_KEY = "demis.code-master.by-group"

SQL = (
    "SELECT CD_GRP_ID, CD_VAL, CD_NM, CD_NM_ENG, USE_YN, SORT_NO, REG_DT "
    "FROM DEMIS_OWNER.TB_CD_MST "
    "WHERE CD_GRP_ID = :cd_grp_id "
    "ORDER BY SORT_NO"
)

TEMPLATE = {
    "stable_key": STABLE_KEY,
    "name": "공통 코드 그룹별 조회",
    "description": "DEMIS 공통 코드 마스터에서 사용자가 요청한 코드 그룹의 코드값, 코드명 및 사용 여부를 조회한다.",
    "source_name": SOURCE,
    "target_schemas": ["DEMIS_OWNER"],
    "sql_text": SQL,
    "parameter_schema": [
        {
            "name": "cd_grp_id",
            "label": "코드 그룹",
            "description": "조회할 공통 코드 그룹 ID. 예: DQA_TEST",
            "type": "string",
            "required": True,
            "pattern": "^[A-Za-z0-9_]+$",
            "sensitive": False,
        }
    ],
    "row_limit": 100,
    "timeout_seconds": 30,
}

HEADERS = {
    "X-DQA-Dev-Actor": "dqa-oracle-mock-bootstrap",
    "X-DQA-Dev-Roles": "administrator",
}


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def request_json(
    method: str,
    path: str,
    *,
    payload: dict | None = None,
    query: dict[str, str] | None = None,
) -> dict | list:
    url = f"{base_url}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)

    data = None
    headers = dict(HEADERS)

    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
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
        return json.loads(raw)
    except Exception:
        fail(f"{method} {path} returned invalid JSON")


def require_object(value: object, context: str) -> dict:
    if not isinstance(value, dict):
        fail(f"{context} returned non-object JSON")
    return value


def validate_profile(profile: dict) -> None:
    for key, expected in PROFILE.items():
        actual = profile.get(key)
        if actual != expected:
            fail(
                f"existing Connection Profile differs at {key}: "
                f"expected={expected!r}, actual={actual!r}"
            )


def validate_template(detail: dict) -> None:
    expected_top = {
        "stable_key": TEMPLATE["stable_key"],
        "name": TEMPLATE["name"],
        "description": TEMPLATE["description"],
        "source_name": TEMPLATE["source_name"],
        "target_schemas": TEMPLATE["target_schemas"],
    }
    for key, expected in expected_top.items():
        actual = detail.get(key)
        if actual != expected:
            fail(
                f"existing Query Template differs at {key}: "
                f"expected={expected!r}, actual={actual!r}"
            )

    version = require_object(detail.get("version"), "template version")

    if version.get("sql_text") != TEMPLATE["sql_text"]:
        fail("existing Query Template SQL differs from bootstrap fixture")

    if version.get("row_limit") != TEMPLATE["row_limit"]:
        fail("existing Query Template row_limit differs from bootstrap fixture")

    if version.get("timeout_seconds") != TEMPLATE["timeout_seconds"]:
        fail("existing Query Template timeout differs from bootstrap fixture")

    params = version.get("parameter_schema")
    if not isinstance(params, list) or len(params) != 1:
        fail("existing Query Template parameter schema differs from fixture")

    param = require_object(params[0], "template parameter")
    expected_param = TEMPLATE["parameter_schema"][0]

    for key, expected in expected_param.items():
        actual = param.get(key)
        if actual != expected:
            fail(
                f"existing Query Template parameter differs at {key}: "
                f"expected={expected!r}, actual={actual!r}"
            )

    compatibility = require_object(
        version.get("compatibility"),
        "template compatibility",
    )
    if compatibility.get("compatible") is not True:
        fail("existing Query Template is incompatible with the active Catalog")


active = require_object(
    request_json(
        "GET",
        f"/api/v1/catalog/active/{urllib.parse.quote(SOURCE, safe='')}",
    ),
    "active Catalog",
)

if active.get("source_name") != SOURCE:
    fail("active Catalog source does not match Oracle mock source")

if active.get("package_readiness") != "READY":
    fail("active Catalog is not READY")

print(
    "PASS: active Catalog "
    f"revision_id={active.get('revision_id')} "
    f"fingerprint={active.get('schema_fingerprint')}"
)

profiles = require_object(
    request_json(
        "GET",
        "/api/v1/connection-profiles",
        query={
            "source_name": SOURCE,
            "environment": ENVIRONMENT,
        },
    ),
    "Connection Profile list",
)

items = profiles.get("items")
if not isinstance(items, list):
    fail("Connection Profile list does not contain items")

if len(items) > 1:
    fail("multiple Connection Profiles exist for Oracle mock development target")

if not items:
    profile = require_object(
        request_json(
            "POST",
            "/api/v1/connection-profiles",
            payload=PROFILE,
        ),
        "created Connection Profile",
    )
    print(f"PASS: created Connection Profile id={profile.get('id')}")
else:
    profile = require_object(items[0], "existing Connection Profile")
    validate_profile(profile)
    print(f"PASS: existing Connection Profile id={profile.get('id')} matches fixture")

profile_id = profile.get("id")
if not isinstance(profile_id, int):
    fail("Connection Profile id is missing")

if profile.get("enabled") is not True:
    profile = require_object(
        request_json(
            "POST",
            f"/api/v1/connection-profiles/{profile_id}/enable",
        ),
        "enabled Connection Profile",
    )
    print(f"PASS: enabled Connection Profile id={profile_id}")
else:
    print(f"PASS: Connection Profile id={profile_id} already enabled")

templates = require_object(
    request_json(
        "GET",
        "/api/v1/query-templates",
        query={"source_name": SOURCE},
    ),
    "Query Template list",
)

template_items = templates.get("items")
if not isinstance(template_items, list):
    fail("Query Template list does not contain items")

matches = [
    item
    for item in template_items
    if isinstance(item, dict) and item.get("stable_key") == STABLE_KEY
]

if len(matches) > 1:
    fail(f"multiple Query Templates found for stable_key={STABLE_KEY}")

if not matches:
    detail = require_object(
        request_json(
            "POST",
            "/api/v1/query-templates",
            payload=TEMPLATE,
        ),
        "created Query Template",
    )
    print(f"PASS: created Query Template id={detail.get('id')}")
else:
    template_id = matches[0].get("id")
    if not isinstance(template_id, int):
        fail("existing Query Template id is missing")

    detail = require_object(
        request_json(
            "GET",
            f"/api/v1/query-templates/{template_id}",
        ),
        "existing Query Template",
    )
    validate_template(detail)
    print(f"PASS: existing Query Template id={template_id} matches fixture")

template_id = detail.get("id")
if not isinstance(template_id, int):
    fail("Query Template id is missing")

validate_template(detail)

status = detail.get("approval_status")

if status == "DRAFT":
    detail = require_object(
        request_json(
            "POST",
            f"/api/v1/query-templates/{template_id}/submit-review",
        ),
        "submitted Query Template",
    )
    status = detail.get("approval_status")
    print("PASS: Query Template submitted for review")

if status == "IN_REVIEW":
    detail = require_object(
        request_json(
            "POST",
            f"/api/v1/query-templates/{template_id}/approve",
        ),
        "approved Query Template",
    )
    status = detail.get("approval_status")
    print("PASS: Query Template approved")

if status == "REJECTED":
    fail("existing Query Template is REJECTED; bootstrap will not override it")

if status != "APPROVED":
    fail(f"unexpected Query Template approval status: {status!r}")

if detail.get("enabled") is not True:
    detail = require_object(
        request_json(
            "POST",
            f"/api/v1/query-templates/{template_id}/enable",
        ),
        "enabled Query Template",
    )
    print("PASS: Query Template enabled")
else:
    print("PASS: Query Template already enabled")

validate_template(detail)

print(
    "PASS: Oracle mock DQA metadata bootstrap complete "
    f"profile_id={profile_id} template_id={template_id}"
)
PY
