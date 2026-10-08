"""Phase 28-C: Template Query MCP tools (prepare_query / execute_query)."""

from __future__ import annotations

import base64
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from mcp.server.fastmcp.exceptions import ToolError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.demis.fake import FakeCredentialResolver, FakeReadOnlyDemisAdapter
from app.adapters.execution.errors import ExecutionErrorCode, ExecutionPreviewErrorCode
from app.auth.errors import AuthErrorCode
from app.auth.models import AuthenticatedActor, Permission, Role
from app.core.config import Settings, get_settings
from app.mcp.adapter import McpApplicationAdapter
from app.mcp.execution_token import (
    McpExecutionTokenError,
    McpExecutionTokenErrorCode,
    issue_execution_token,
    verify_execution_token,
)
from app.mcp.registry import build_foundation_registry
from app.models.query_audit import QueryAuditEvent
from app.schemas.audit import QueryAuditEventCreate
from app.services.catalog_active import activate_catalog_revision
from app.services.catalog_package_import import import_catalog_package_bytes
from tests.catalog_package_fixtures import (
    DEFAULT_SOURCE,
    build_core_documents,
    build_package_zip,
)

pytestmark = pytest.mark.integration

SOURCE = dict(DEFAULT_SOURCE)
ENVIRONMENT = "dev"
ALLOWED_REF = "env:DEMIS_SECRET_PASSWORD"

_MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "X-DQA-Dev-Actor": "mcp-operator",
    "X-DQA-Dev-Roles": "query_operator",
}


def _clear_caches() -> None:
    from app.adapters.db.session import get_engine, get_session_factory

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


def _token_key_b64() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


@pytest.fixture()
def mcp_query_env(
    monkeypatch: pytest.MonkeyPatch, test_settings_env: dict[str, str]
) -> dict[str, str]:
    key = _token_key_b64()
    monkeypatch.setenv("DQA_MCP_ENABLED", "true")
    monkeypatch.setenv("DQA_MCP_MOUNT_PATH", "/mcp")
    monkeypatch.setenv("DQA_MCP_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("DQA_AUTH_PROVIDER", "dev_headers")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DQA_MCP_QUERY_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("DQA_MCP_EXECUTION_TOKEN_KEY", key)
    monkeypatch.setenv("DQA_MCP_EXECUTION_TOKEN_TTL_SECONDS", "300")
    monkeypatch.setenv("DEMIS_SECRET_PASSWORD", "test-secret-value")
    _clear_caches()
    return {"token_key": key}


@pytest.fixture()
def mcp_db_client(mcp_query_env: dict[str, str], db_session: Session) -> TestClient:
    from app.main import create_app

    _clear_caches()
    application = create_app(check_migrations_on_startup=False)
    with TestClient(application) as client:
        yield client
    _clear_caches()


def _headers(actor: str, roles: str) -> dict[str, str]:
    return {"X-DQA-Dev-Actor": actor, "X-DQA-Dev-Roles": roles}


def _mcp_post(
    client: TestClient,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
) -> Any:
    return client.post(
        "/mcp/",
        headers={**_MCP_HEADERS, **(headers or {})},
        json=payload,
    )


def _tool_call(
    client: TestClient,
    name: str,
    arguments: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    call_id: int = 10,
) -> Any:
    return _mcp_post(
        client,
        {
            "jsonrpc": "2.0",
            "id": call_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        headers=headers,
    )


def _extract_tool_payload(response_json: dict[str, Any]) -> dict[str, Any]:
    result = response_json.get("result")
    if isinstance(result, dict):
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            return structured
        content = result.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if isinstance(text, str) and text.strip().startswith("{"):
                    return json.loads(text)
    raise AssertionError(f"unexpected tools/call payload: {response_json}")


def _tool_is_error(response_json: dict[str, Any]) -> bool:
    result = response_json.get("result")
    return isinstance(result, dict) and result.get("isError") is True


def _assert_no_sensitive_leak(payload: object) -> None:
    text = str(payload).lower()
    forbidden = (
        "api_key",
        "bearer ",
        "password",
        "secret-value",
        "demis.internal.example",
        "select ward_cd",
        "postgresql://",
        '"a01"',  # sensitive ward value when quoted in dumps
    )
    for token in forbidden:
        assert token not in text, f"sensitive token leaked: {token}"


def _import_and_activate(session: Session, *, fingerprint: str):
    files = build_core_documents(
        source=SOURCE,
        fingerprint=fingerprint,
        tables=[{"schema": "DEMIS_OWNER", "name": "T1"}],
    )
    archive = build_package_zip(
        package_readiness="READY",
        source=SOURCE,
        fingerprint=fingerprint,
        files=files,
    )
    revision, created = import_catalog_package_bytes(archive, session)
    assert created is True
    activate_catalog_revision(session, revision.id)
    session.flush()
    return revision


def _template_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "stable_key": "mcp.exec.wards",
        "name": "병동 조회",
        "description": "병동 조회",
        "source_name": SOURCE["source_name"],
        "target_schemas": ["DEMIS_OWNER"],
        "sql_text": (
            "SELECT ward_cd FROM dual WHERE ward_cd = :ward_cd "
            "AND from_date = :from_date"
        ),
        "parameter_schema": [
            {
                "name": "ward_cd",
                "label": "병동 코드",
                "type": "string",
                "required": True,
                "sensitive": True,
                "pattern": r"^[A-Z][0-9]{2}$",
            },
            {
                "name": "from_date",
                "label": "시작일",
                "type": "date",
                "required": False,
                "default": "2024-01-01",
            },
        ],
        "row_limit": 50,
        "timeout_seconds": 15,
    }
    body.update(overrides)
    return body


def _setup_eligible(
    db_session: Session,
    db_client: TestClient,
    *,
    fingerprint: str = "fp-mcp-tpl-query",
    template_overrides: dict[str, Any] | None = None,
    profile_overrides: dict[str, Any] | None = None,
    enable_template: bool = True,
) -> dict[str, Any]:
    revision = _import_and_activate(db_session, fingerprint=fingerprint)
    db_session.commit()
    admin = _headers("admin", "administrator")
    created = db_client.post(
        "/api/v1/query-templates",
        json=_template_body(**(template_overrides or {})),
        headers=admin,
    )
    assert created.status_code == 201, created.text
    detail = created.json()
    if enable_template:
        assert (
            db_client.post(
                f"/api/v1/query-templates/{detail['id']}/submit-review",
                json={},
                headers=admin,
            ).status_code
            == 200
        )
        assert (
            db_client.post(
                f"/api/v1/query-templates/{detail['id']}/approve",
                json={},
                headers=admin,
            ).status_code
            == 200
        )
        enabled = db_client.post(
            f"/api/v1/query-templates/{detail['id']}/enable", headers=admin
        )
        assert enabled.status_code == 200
        detail = enabled.json()
    profile = _ensure_profile_admin(db_client, **(profile_overrides or {}))
    return {
        "revision": revision,
        "template": detail,
        "profile": profile,
        "version_id": detail["version"]["id"],
        "template_id": detail["id"],
    }


def _ensure_profile_admin(db_client: TestClient, **overrides: Any) -> dict[str, Any]:
    admin = _headers("admin", "administrator")
    enabled = overrides.pop("enabled", True)
    body: dict[str, Any] = {
        "name": "Mock DEMIS profile",
        "source_name": SOURCE["source_name"],
        "environment": ENVIRONMENT,
        "dbms_type": "oracle",
        "host": "demis.internal.example",
        "port": 1521,
        "database_name": "DEMIS",
        "username": "dqa_ro",
        "credential_secret_ref": ALLOWED_REF,
    }
    body.update(overrides)
    payload = {key: value for key, value in body.items() if value is not None}
    created = db_client.post(
        "/api/v1/connection-profiles", json=payload, headers=admin
    )
    assert created.status_code == 201, created.text
    profile_id = created.json()["id"]
    if enabled:
        enabled_resp = db_client.post(
            f"/api/v1/connection-profiles/{profile_id}/enable", headers=admin
        )
        assert enabled_resp.status_code == 200
        return enabled_resp.json()
    return created.json()


def _operator() -> AuthenticatedActor:
    return AuthenticatedActor(
        actor_id="mcp-operator",
        roles=frozenset({Role.QUERY_OPERATOR}),
        provider="dev_headers",
    )


def _patch_live_adapter(monkeypatch: pytest.MonkeyPatch) -> FakeReadOnlyDemisAdapter:
    adapter = FakeReadOnlyDemisAdapter(
        rows=[{"ward_cd": "A01"}, {"ward_cd": "B02"}],
        elapsed_ms=12,
    )
    monkeypatch.setattr(
        "app.services.execution_eligibility.is_concrete_demis_adapter_available",
        lambda dbms_type: True,
    )
    monkeypatch.setattr(
        "app.services.query_execution.create_readonly_demis_adapter",
        lambda profile, credential_resolver: adapter,
    )
    monkeypatch.setattr(
        "app.adapters.demis.credential_factory.create_credential_resolver",
        lambda settings=None: FakeCredentialResolver(
            {ALLOWED_REF: "test-secret-value"}
        ),
    )
    return adapter


def test_registry_query_operate_permissions() -> None:
    registry = build_foundation_registry()
    assert registry.get("demis.prepare_query").permission == Permission.QUERY_OPERATE
    assert registry.get("demis.execute_query").permission == Permission.QUERY_OPERATE


def test_prepare_query_operate_denied_at_middleware(
    mcp_db_client: TestClient, db_session: Session
) -> None:
    fixture = _setup_eligible(db_session, mcp_db_client)
    denied = _tool_call(
        mcp_db_client,
        "demis.prepare_query",
        {
            "source_name": SOURCE["source_name"],
            "environment": ENVIRONMENT,
            "template_id": fixture["template_id"],
            "version_id": fixture["version_id"],
            "parameters": {"ward_cd": "A01"},
        },
        headers=_headers("viewer", "viewer"),
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED
    _assert_no_sensitive_leak(denied.json())


def test_prepare_ready_needs_clarification_blocked(
    mcp_db_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _setup_eligible(db_session, mcp_db_client)
    monkeypatch.setattr(
        "app.adapters.demis.factory.create_readonly_demis_adapter",
        MagicMock(side_effect=AssertionError("DEMIS must not be called on prepare")),
    )
    monkeypatch.setattr(
        "app.services.execution_eligibility.is_concrete_demis_adapter_available",
        lambda dbms_type: True,
    )

    ready = _tool_call(
        mcp_db_client,
        "demis.prepare_query",
        {
            "source_name": SOURCE["source_name"],
            "environment": ENVIRONMENT,
            "template_id": fixture["template_id"],
            "version_id": fixture["version_id"],
            "parameters": {"ward_cd": "A01"},
        },
    )
    assert ready.status_code == 200
    assert not _tool_is_error(ready.json())
    ready_payload = _extract_tool_payload(ready.json())
    assert ready_payload["status"] == "READY"
    assert ready_payload["execution_token"]
    assert ready_payload["token_expires_at"]
    assert ready_payload["catalog_revision_id"] == fixture["revision"].id
    assert ready_payload["catalog_fingerprint"] == "fp-mcp-tpl-query"
    assert "sql_text" not in ready_payload
    assert "resolved_parameters" not in ready_payload
    assert "A01" not in json.dumps(ready_payload)
    assert "ward_cd" in ready_payload["sensitive_parameter_names"]
    _assert_no_sensitive_leak(ready_payload)

    clarify = _tool_call(
        mcp_db_client,
        "demis.prepare_query",
        {
            "source_name": SOURCE["source_name"],
            "environment": ENVIRONMENT,
            "template_id": fixture["template_id"],
            "version_id": fixture["version_id"],
            "parameters": {},
        },
        call_id=11,
    )
    clarify_payload = _extract_tool_payload(clarify.json())
    assert clarify_payload["status"] == "NEEDS_CLARIFICATION"
    assert clarify_payload["execution_token"] is None
    assert clarify_payload["error"]["code"] == ExecutionPreviewErrorCode.PARAMETER_INVALID
    _assert_no_sensitive_leak(clarify_payload)

    # Soft adapter blocker → BLOCKED (eligibility succeeds, execution unavailable).
    monkeypatch.setattr(
        "app.services.execution_eligibility.is_concrete_demis_adapter_available",
        lambda dbms_type: False,
    )
    blocked = _tool_call(
        mcp_db_client,
        "demis.prepare_query",
        {
            "source_name": SOURCE["source_name"],
            "environment": ENVIRONMENT,
            "template_id": fixture["template_id"],
            "version_id": fixture["version_id"],
            "parameters": {"ward_cd": "A01"},
        },
        call_id=12,
    )
    blocked_payload = _extract_tool_payload(blocked.json())
    assert blocked_payload["status"] == "BLOCKED"
    assert blocked_payload["execution_token"] is None
    assert "DEMIS_ADAPTER_UNAVAILABLE" in blocked_payload["blockers"]
    _assert_no_sensitive_leak(blocked_payload)


def test_prepare_without_demis_side_effects(
    db_session: Session,
    mcp_db_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _setup_eligible(db_session, mcp_db_client, fingerprint="fp-mcp-noside")
    resolve = MagicMock(side_effect=AssertionError("credentials must not resolve"))
    monkeypatch.setattr(
        "app.services.execution_eligibility.is_concrete_demis_adapter_available",
        lambda dbms_type: True,
    )
    monkeypatch.setattr(
        "app.adapters.demis.env_credentials.EnvironmentCredentialResolver.resolve",
        resolve,
        raising=False,
    )
    monkeypatch.setattr(
        "app.adapters.demis.factory.create_readonly_demis_adapter",
        MagicMock(side_effect=AssertionError("adapter must not be created")),
    )
    audit = MagicMock(side_effect=AssertionError("audit must not write on prepare"))
    monkeypatch.setattr(
        "app.services.query_audit.record_query_audit_event_durable",
        audit,
        raising=False,
    )

    result = McpApplicationAdapter().prepare_query(
        _operator(),
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
        template_id=fixture["template_id"],
        version_id=fixture["version_id"],
        parameters={"ward_cd": "A01"},
        session=db_session,
    )
    assert result["status"] == "READY"
    resolve.assert_not_called()
    audit.assert_not_called()


def test_token_tampering_expiry_wrong_actor_missing_key(
    mcp_query_env: dict[str, str],
    db_session: Session,
    mcp_db_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _setup_eligible(db_session, mcp_db_client, fingerprint="fp-mcp-token")
    monkeypatch.setattr(
        "app.services.execution_eligibility.is_concrete_demis_adapter_available",
        lambda dbms_type: True,
    )
    settings = get_settings()
    actor = _operator()
    token, _ = issue_execution_token(
        actor=actor,
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
        template_id=fixture["template_id"],
        version_id=fixture["version_id"],
        catalog_revision_id=fixture["revision"].id,
        catalog_fingerprint="fp-mcp-token",
        connection_profile_id=fixture["profile"]["id"],
        parameters={"ward_cd": "A01", "from_date": "2024-01-01"},
        sensitive_parameter_names=["ward_cd"],
        settings=settings,
    )

    # Tamper ciphertext.
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(McpExecutionTokenError) as tamper_exc:
        verify_execution_token(tampered, actor=actor, settings=settings)
    assert tamper_exc.value.code == McpExecutionTokenErrorCode.INVALID

    # Wrong actor.
    other = AuthenticatedActor(
        actor_id="other-op",
        roles=frozenset({Role.QUERY_OPERATOR}),
        provider="dev_headers",
    )
    with pytest.raises(McpExecutionTokenError) as subject_exc:
        verify_execution_token(token, actor=other, settings=settings)
    assert subject_exc.value.code == McpExecutionTokenErrorCode.SUBJECT_MISMATCH

    # Expired: issue with TTL then rewind claims via monkeypatched now is hard;
    # craft settings with ttl and manually build expired by verifying after wait=0
    # using issue with patched datetime inside verify by setting exp in past via
    # decrypt isn't possible. Instead call verify with a freshly issued token
    # after monkeypatching datetime in execution_token.
    real_now = datetime.now(UTC)

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return real_now + timedelta(seconds=400)

    monkeypatch.setattr("app.mcp.execution_token.datetime", _FrozenDateTime)
    with pytest.raises(McpExecutionTokenError) as exp_exc:
        verify_execution_token(token, actor=actor, settings=settings)
    assert exp_exc.value.code == McpExecutionTokenErrorCode.EXPIRED

    # Missing key fail-closed.
    monkeypatch.delenv("DQA_MCP_EXECUTION_TOKEN_KEY", raising=False)
    _clear_caches()
    bare = Settings(
        APP_ENV="test",
        DQA_MCP_EXECUTION_TOKEN_KEY=None,
        DQA_MCP_EXECUTION_TOKEN_TTL_SECONDS=300,
    )
    with pytest.raises(McpExecutionTokenError) as key_exc:
        issue_execution_token(
            actor=actor,
            source_name=SOURCE["source_name"],
            environment=ENVIRONMENT,
            template_id=1,
            version_id=1,
            catalog_revision_id=1,
            catalog_fingerprint="x",
            connection_profile_id=1,
            parameters={},
            sensitive_parameter_names=[],
            settings=bare,
        )
    assert key_exc.value.code == McpExecutionTokenErrorCode.KEY_UNAVAILABLE


def test_revoked_template_and_stale_revision_and_profile_change(
    mcp_db_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _setup_eligible(db_session, mcp_db_client, fingerprint="fp-mcp-stale")
    monkeypatch.setattr(
        "app.services.execution_eligibility.is_concrete_demis_adapter_available",
        lambda dbms_type: True,
    )
    adapter = McpApplicationAdapter()
    actor = _operator()
    prepared = adapter.prepare_query(
        actor,
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
        template_id=fixture["template_id"],
        version_id=fixture["version_id"],
        parameters={"ward_cd": "A01"},
        session=db_session,
    )
    assert prepared["status"] == "READY"
    token = prepared["execution_token"]

    # Revoke / disable template.
    admin = _headers("admin", "administrator")
    disabled = mcp_db_client.post(
        f"/api/v1/query-templates/{fixture['template_id']}/disable",
        headers=admin,
    )
    assert disabled.status_code == 200
    revoked = adapter.prepare_query(
        actor,
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
        template_id=fixture["template_id"],
        version_id=fixture["version_id"],
        parameters={"ward_cd": "A01"},
        session=db_session,
    )
    assert revoked["status"] == "BLOCKED"
    assert revoked["error"]["code"] == ExecutionPreviewErrorCode.TEMPLATE_NOT_ELIGIBLE

    # Re-enable for fingerprint drift test on execute binding.
    enabled = mcp_db_client.post(
        f"/api/v1/query-templates/{fixture['template_id']}/enable",
        headers=admin,
    )
    assert enabled.status_code == 200
    # Change active catalog fingerprint pointer by activating a new revision
    # without updating the template → CATALOG_MISMATCH on prepare/execute.
    new_rev = _import_and_activate(db_session, fingerprint="fp-mcp-stale-b")
    db_session.commit()
    assert new_rev.id != fixture["revision"].id
    stale = adapter.prepare_query(
        actor,
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
        template_id=fixture["template_id"],
        version_id=fixture["version_id"],
        parameters={"ward_cd": "A01"},
        session=db_session,
    )
    assert stale["status"] == "BLOCKED"
    assert stale["error"]["code"] == ExecutionPreviewErrorCode.CATALOG_MISMATCH

    # Restore original active revision for profile-change execute path.
    activate_catalog_revision(db_session, fixture["revision"].id)
    db_session.commit()
    # Disable profile → prepare BLOCKED.
    mcp_db_client.post(
        f"/api/v1/connection-profiles/{fixture['profile']['id']}/disable",
        headers=admin,
    )
    profile_blocked = adapter.prepare_query(
        actor,
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
        template_id=fixture["template_id"],
        version_id=fixture["version_id"],
        parameters={"ward_cd": "A01"},
        session=db_session,
    )
    assert profile_blocked["status"] == "BLOCKED"
    assert (
        profile_blocked["error"]["code"]
        == ExecutionPreviewErrorCode.CONNECTION_PROFILE_DISABLED
    )

    # Execute with old token while profile disabled → binding/eligibility fail closed.
    mcp_db_client.post(
        f"/api/v1/connection-profiles/{fixture['profile']['id']}/enable",
        headers=admin,
    )
    # First ensure execute works path uses token; then disable and expect tool error.
    mcp_db_client.post(
        f"/api/v1/connection-profiles/{fixture['profile']['id']}/disable",
        headers=admin,
    )
    with pytest.raises(ToolError) as exc_info:
        adapter.execute_query(actor, execution_token=token, session=db_session)
    assert ExecutionPreviewErrorCode.CONNECTION_PROFILE_DISABLED in str(exc_info.value)


def test_execute_reuses_safety_adapter_audit_and_fail_closed_audit(
    mcp_db_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _setup_eligible(db_session, mcp_db_client, fingerprint="fp-mcp-exec")
    _patch_live_adapter(monkeypatch)
    adapter = McpApplicationAdapter()
    actor = _operator()
    prepared = adapter.prepare_query(
        actor,
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
        template_id=fixture["template_id"],
        version_id=fixture["version_id"],
        parameters={"ward_cd": "A01"},
        session=db_session,
    )
    assert prepared["status"] == "READY"
    result = adapter.execute_query(
        actor,
        execution_token=prepared["execution_token"],
        session=db_session,
    )
    assert result["row_count"] == 2
    assert result["columns"] == ["ward_cd"]
    assert "sql_text" not in result
    assert "host" not in result
    events = list(db_session.scalars(select(QueryAuditEvent)).all())
    assert any(e.event_type == "QUERY_REQUEST" and e.status == "SUCCEEDED" for e in events)
    assert any(e.event_type == "QUERY_EXECUTION" and e.status == "SUCCEEDED" for e in events)
    for event in events:
        assert "A01" not in str(event.parameter_names)

    # Audit failure fail-closed (required STARTED write).
    prepared2 = adapter.prepare_query(
        actor,
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
        template_id=fixture["template_id"],
        version_id=fixture["version_id"],
        parameters={"ward_cd": "B02"},
        session=db_session,
    )

    def _boom_audit(_payload: QueryAuditEventCreate) -> object:
        raise RuntimeError("audit down")

    with pytest.raises(ToolError) as audit_exc:
        adapter.execute_query(
            actor,
            execution_token=prepared2["execution_token"],
            session=db_session,
            audit_writer=_boom_audit,
        )
    err = str(audit_exc.value)
    assert ExecutionErrorCode.AUDIT_UNAVAILABLE in err
    assert "audit down" not in err
    assert "B02" not in err
    assert "A01" not in err


def test_execute_disabled_and_leakage_regression(
    mcp_db_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _setup_eligible(db_session, mcp_db_client, fingerprint="fp-mcp-leak")
    monkeypatch.setattr(
        "app.services.execution_eligibility.is_concrete_demis_adapter_available",
        lambda dbms_type: True,
    )
    adapter = McpApplicationAdapter()
    actor = _operator()
    prepared = adapter.prepare_query(
        actor,
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
        template_id=fixture["template_id"],
        version_id=fixture["version_id"],
        parameters={"ward_cd": "A01"},
        session=db_session,
    )
    assert "A01" not in json.dumps(prepared)
    assert prepared["execution_token"].startswith("dqa1.")
    # Token ciphertext must not contain plaintext parameter.
    assert b"A01" not in prepared["execution_token"].encode("utf-8")

    monkeypatch.setenv("DQA_MCP_QUERY_EXECUTION_ENABLED", "false")
    _clear_caches()
    with pytest.raises(ToolError) as disabled:
        adapter.execute_query(
            actor,
            execution_token=prepared["execution_token"],
            session=db_session,
            settings=get_settings(),
        )
    assert "MCP_QUERY_EXECUTION_DISABLED" in str(disabled.value)


def test_web_execution_preview_regression(
    mcp_db_client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Web preview path remains intact alongside MCP Template Query tools."""
    fixture = _setup_eligible(db_session, mcp_db_client, fingerprint="fp-mcp-web")
    monkeypatch.setattr(
        "app.services.execution_eligibility.is_concrete_demis_adapter_available",
        lambda dbms_type: True,
    )
    admin = _headers("ops", "query_operator")
    preview = mcp_db_client.post(
        "/api/v1/query-executions/preview",
        headers=admin,
        json={
            "source_name": SOURCE["source_name"],
            "environment": ENVIRONMENT,
            "template_id": fixture["template_id"],
            "version_id": fixture["version_id"],
            "parameters": {"ward_cd": "A01"},
        },
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["execution_available"] is True
    assert "sql_text" not in preview.json()
