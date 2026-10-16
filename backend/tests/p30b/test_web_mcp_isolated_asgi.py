"""P30-B: genuine Web + MCP ASGI requests on ONE marker-verified disposable PG.

Only runner scripts/dqa-p30b-disposable-asgi-check.sh may provision the
ephemeral database. Subdirectory conftest fail-closes BEFORE the root db_session
fixture can truncate the known tables. Oracle is ALWAYS the test-only fake
adapter; this does NOT authorize, reach, or verify real DEMIS / EMR.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.demis.fake import FakeReadOnlyDemisAdapter
from app.adapters.db.session import get_session_factory
from app.core.config import get_settings
from app.models.query_audit import QueryAuditEvent
from tests import test_mcp_template_query as existing

pytestmark = pytest.mark.integration

WEB = "/api/v1/query-executions/execute"
ADMIN = existing._headers("synthetic-admin", "administrator")
OPERATOR = existing._headers("mcp-operator", "query_operator")
SOURCE = existing.SOURCE["source_name"]


@pytest.fixture()
def asgi_client(test_settings_env: dict[str, str], db_session: Session) -> TestClient:
    """Use the existing app/routes with an already migrated isolated database."""
    from app.main import create_app

    existing._clear_caches()
    assert get_settings().dqa_db_name == "dqa_p30b_disposable"
    app = create_app(check_migrations_on_startup=True)
    with TestClient(app) as client:
        yield client
    existing._clear_caches()


def _setup(db_session: Session, client: TestClient, *, fingerprint: str) -> dict[str, Any]:
    return existing._setup_eligible(
        db_session,
        client,
        fingerprint=fingerprint,
        template_overrides={"row_limit": 1, "timeout_seconds": 8},
    )


def _body(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_name": SOURCE,
        "environment": existing.ENVIRONMENT,
        "template_id": data["template_id"],
        "version_id": data["version_id"],
        "parameters": {"ward_cd": "A01"},
    }


def _prepare(client: TestClient, data: dict[str, Any]) -> str:
    res = existing._tool_call(client, "demis.prepare_query", _body(data))
    assert res.status_code == 200, res.text
    assert not existing._tool_is_error(res.json()), res.text
    payload = existing._extract_tool_payload(res.json())
    assert payload["status"] == "READY", payload
    assert payload["execution_token"].startswith("dqa1.")
    assert "A01" not in json.dumps(payload)
    existing._assert_no_sensitive_leak(payload)
    return payload["execution_token"]


def _execute_mcp(client: TestClient, token: str) -> Any:
    return existing._tool_call(client, "demis.execute_query", {"execution_token": token})


def _audit(audit_id: str) -> list[QueryAuditEvent]:
    """Read with a NEW independent PostgreSQL session after ASGI request."""
    with get_session_factory()() as session:
        return list(session.scalars(
            select(QueryAuditEvent)
            .where(QueryAuditEvent.audit_id == audit_id)
            .order_by(QueryAuditEvent.id)
        ).all())


def _assert_audit(rows: list[QueryAuditEvent], *, final: str, category: str | None = None) -> None:
    assert [(r.event_type, r.status) for r in rows] == [
        ("QUERY_REQUEST", "STARTED"),
        ("QUERY_REQUEST", "SUCCEEDED"),
        ("QUERY_EXECUTION", "STARTED"),
        ("QUERY_EXECUTION", final),
    ]
    assert rows[-1].failure_category == category
    assert all(r.parameter_logging_policy == "NAMES_ONLY" for r in rows)
    assert all(r.source_name == SOURCE for r in rows)
    for r in rows:
        value = repr(r)
        for secret in ("test-secret-value", "demis.internal.example", "SELECT ward_cd"):
            assert secret not in value
        assert "A01" not in json.dumps(r.parameter_names)
    assert rows[-1].parameter_names == ["ward_cd", "from_date"]
    assert rows[-1].sensitive_parameter_names == ["ward_cd"]


def test_web_mcp_asgi_equivalent_bounded_query_and_durable_audit(
    db_session: Session,
    asgi_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _setup(db_session, asgi_client, fingerprint="p30b-parity")
    fake: FakeReadOnlyDemisAdapter = existing._patch_live_adapter(monkeypatch)
    token = _prepare(asgi_client, data)

    web = asgi_client.post(WEB, json=_body(data), headers=OPERATOR)
    assert web.status_code == 200, web.text
    assert web.headers["cache-control"] == "no-store, private"
    web_result = web.json()

    mcp = _execute_mcp(asgi_client, token)
    assert mcp.status_code == 200, mcp.text
    assert not existing._tool_is_error(mcp.json()), mcp.text
    mcp_result = existing._extract_tool_payload(mcp.json())

    for payload in (web_result, mcp_result):
        assert payload["row_count"] == 1
        assert payload["rows"] == [{"ward_cd": "A01"}]
        assert payload["truncated"] is True
        assert payload["columns"] == ["ward_cd"]
        existing._assert_no_sensitive_leak({
            key: value for key, value in payload.items()
            if key not in {"rows"}
        })
    assert {k: v for k, v in web_result.items() if k != "audit_id"} == {
        k: v for k, v in mcp_result.items() if k != "audit_id"
    }
    assert fake.last_row_limit == 1
    assert fake.last_timeout_seconds == 8
    assert fake.last_parameters == {"ward_cd": "A01", "from_date": "2024-01-01"}

    for audit_id in (web_result["audit_id"], mcp_result["audit_id"]):
        _assert_audit(_audit(audit_id), final="SUCCEEDED")

    # Distinct correlation IDs prove two independent durable audit lifecycles.
    assert web_result["audit_id"] != mcp_result["audit_id"]


def test_web_mcp_real_asgi_rejects_disabled_profile_before_any_mock_call(
    db_session: Session, asgi_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _setup(db_session, asgi_client, fingerprint="p30b-revoked-profile")
    fake = existing._patch_live_adapter(monkeypatch)
    token = _prepare(asgi_client, data)
    disabled = asgi_client.post(
        f"/api/v1/connection-profiles/{data['profile']['id']}/disable",
        headers=ADMIN,
    )
    assert disabled.status_code == 200, disabled.text

    web = asgi_client.post(WEB, json=_body(data), headers=OPERATOR)
    assert web.status_code == 409, web.text
    assert "CONNECTION_PROFILE_DISABLED" in web.text

    mcp = _execute_mcp(asgi_client, token)
    assert mcp.status_code == 200
    assert existing._tool_is_error(mcp.json())
    assert "CONNECTION_PROFILE_DISABLED" in json.dumps(mcp.json())

    assert fake.last_sql_text is None
    assert fake.last_parameters is None
    with get_session_factory()() as session:
        events = list(session.scalars(select(QueryAuditEvent).order_by(QueryAuditEvent.id)).all())
    assert [(r.event_type, r.status) for r in events] == [
        ("QUERY_REQUEST", "STARTED"), ("QUERY_REQUEST", "DENIED")
    ]
    assert "A01" not in json.dumps([r.parameter_names for r in events])


def test_web_mcp_asgi_rbac_denies_without_query_audit_or_oracle(
    db_session: Session, asgi_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _setup(db_session, asgi_client, fingerprint="p30b-rbac")
    fake = existing._patch_live_adapter(monkeypatch)
    body = _body(data)
    web = asgi_client.post(
        WEB, json=body, headers=existing._headers("viewer", "viewer"),
    )
    assert web.status_code == 403, web.text

    mcp = existing._tool_call(
        asgi_client, "demis.prepare_query", body,
        headers=existing._headers("viewer", "viewer"),
    )
    assert mcp.status_code == 403, mcp.text
    assert fake.last_sql_text is None
    with get_session_factory()() as session:
        assert session.scalars(select(QueryAuditEvent)).first() is None


def test_web_mcp_asgi_timeout_persists_identical_failure_audit(
    db_session: Session, asgi_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _setup(db_session, asgi_client, fingerprint="p30b-timeout")
    fake = existing._patch_live_adapter(monkeypatch)
    fake._simulate_timeout = True  # Test-only fake adapter simulation, no Oracle I/O.
    token = _prepare(asgi_client, data)

    web = asgi_client.post(WEB, json=_body(data), headers=OPERATOR)
    assert web.status_code == 504, web.text
    assert "TIMEOUT" in web.text

    mcp = _execute_mcp(asgi_client, token)
    assert mcp.status_code == 200, mcp.text
    assert existing._tool_is_error(mcp.json())
    assert "TIMEOUT" in json.dumps(mcp.json())

    with get_session_factory()() as session:
        rows = list(session.scalars(select(QueryAuditEvent).order_by(QueryAuditEvent.id)).all())
    assert len(rows) == 8
    ids = list(dict.fromkeys(r.audit_id for r in rows))
    assert len(ids) == 2
    for audit_id in ids:
        _assert_audit(_audit(audit_id), final="FAILED", category="TIMEOUT")
    for text in (web.text, mcp.text):
        assert "test-secret-value" not in text
        assert "demis.internal.example" not in text
        assert "SELECT ward_cd" not in text
