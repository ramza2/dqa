"""Phase 30-A: Web and MCP share the same read-only execute/audit core.

DB-FREE, network-free integration of two public application entrypoints with
the REAL query-execution service, real AES-GCM token, synthetic eligibility,
test-only DEMIS adapter, and in-memory audit writer.

This is NOT a real HTTP/MCP transport E2E or DEMIS/DBA acceptance test.
Never use the db_session/db_client fixtures (which initialize and truncate DB).
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException, Response
from mcp.server.fastmcp.exceptions import ToolError

from app.adapters.demis.errors import DemisAdapterErrorCode
from app.adapters.demis.fake import FakeReadOnlyDemisAdapter
from app.adapters.demis.profile import ConnectionProfileSnapshot
from app.adapters.execution.errors import (
    ExecutionErrorCode,
    ExecutionPreviewError,
    ExecutionPreviewErrorCode,
)
from app.api.routes import query_executions as web_routes
from app.auth.models import AuthenticatedActor, Role
from app.core.config import Settings
from app.mcp import adapter as mcp_adapter
from app.mcp.execution_token import (
    connection_profile_binding_fingerprint,
    issue_execution_token,
)
from app.schemas.query_execution import QueryExecutionRequest
from app.services.execution_eligibility import ExecutionEligibilityResult
from app.services.query_execution import execute_query as core_execute_query

SOURCE = "synthetic_offline_source"
ENV = "test-only"
SENSITIVE = "SYN-PATIENT-NEVER-LOG"
HOST = "replica.invalid"
SECRET_REF = "env:SYNTHETIC_NOT_REAL"
SQL = "SELECT encounter_id FROM synthetic_encounters WHERE patient_ref = :patient_ref"
AUDIT_OK = [
    ("QUERY_REQUEST", "STARTED"),
    ("QUERY_REQUEST", "SUCCEEDED"),
    ("QUERY_EXECUTION", "STARTED"),
    ("QUERY_EXECUTION", "SUCCEEDED"),
]


def _actor() -> AuthenticatedActor:
    return AuthenticatedActor(
        actor_id="offline-query-operator",
        provider="test",
        roles=frozenset({Role.QUERY_OPERATOR}),
    )


def _profile() -> SimpleNamespace:
    return SimpleNamespace(
        id=41,
        name="synthetic replica only",
        source_name=SOURCE,
        environment=ENV,
        enabled=True,
        dbms_type="oracle",
        host=HOST,
        port=1521,
        database_name="SYNTHETIC_REPLICA",
        username="synthetic_ro",
        credential_secret_ref=SECRET_REF,
    )


def _eligibility() -> ExecutionEligibilityResult:
    return ExecutionEligibilityResult(
        source_name=SOURCE,
        environment=ENV,
        template=SimpleNamespace(id=11),
        version=SimpleNamespace(id=12, version=1, sql_text=SQL),
        catalog_revision_id=51,
        catalog_fingerprint="synthetic-fingerprint-only",
        connection_profile=_profile(),
        parameters=[SimpleNamespace(name="patient_ref")],
        resolved_parameters={"patient_ref": SENSITIVE},
        sensitive_parameter_names=["patient_ref"],
        row_limit=2,
        timeout_seconds=3,
        execution_available=True,
    )


def _request() -> QueryExecutionRequest:
    return QueryExecutionRequest(
        source_name=SOURCE,
        environment=ENV,
        template_id=11,
        version_id=12,
        parameters={"patient_ref": SENSITIVE},
    )


def _settings() -> Settings:
    # No env_file or live service settings; fixed synthetic 256-bit token key.
    key = base64.urlsafe_b64encode(b"s" * 32).decode("ascii")
    return Settings(
        _env_file=None,
        APP_ENV="test",
        DQA_MCP_QUERY_EXECUTION_ENABLED=True,
        DQA_MCP_EXECUTION_TOKEN_KEY=key,
        DQA_MCP_EXECUTION_TOKEN_TTL_SECONDS=300,
    )


@dataclass
class OfflineHarness:
    actor: AuthenticatedActor
    settings: Settings
    request: QueryExecutionRequest
    events: dict[str, list[Any]] = field(default_factory=lambda: {"web": [], "mcp": []})
    instances: dict[str, FakeReadOnlyDemisAdapter] = field(default_factory=dict)
    credential_calls: dict[str, int] = field(default_factory=lambda: {"web": 0, "mcp": 0})
    adapter_calls: dict[str, int] = field(default_factory=lambda: {"web": 0, "mcp": 0})
    eligibility_calls: dict[str, int] = field(default_factory=lambda: {"web": 0, "mcp": 0})
    active_channel: str = ""
    timeout: bool = False
    deny: bool = False
    audit_fail: bool = False

    def eligibility(self, _session: object, **kwargs: Any) -> ExecutionEligibilityResult:
        channel = self.active_channel
        self.eligibility_calls[channel] += 1
        assert kwargs == {
            "source_name": SOURCE,
            "environment": ENV,
            "template_id": 11,
            "version_id": 12,
            "parameters": {"patient_ref": SENSITIVE},
        }
        if self.deny:
            raise ExecutionPreviewError(
                ExecutionPreviewErrorCode.CATALOG_MISMATCH,
                "synthetic catalog revision changed",
            )
        return _eligibility()

    def bridge(self, session: object, request: QueryExecutionRequest, *, actor: AuthenticatedActor):
        channel = self.active_channel
        assert actor == self.actor
        assert request == self.request

        def audit_writer(event: Any) -> None:
            self.events[channel].append(event)
            if self.audit_fail and event.event_type == "QUERY_EXECUTION" and event.status == "STARTED":
                raise RuntimeError("synthetic audit store unavailable")

        def resolver_factory() -> object:
            self.credential_calls[channel] += 1
            return object()

        def adapter_factory(
            profile: ConnectionProfileSnapshot, *, credential_resolver: object,
        ) -> FakeReadOnlyDemisAdapter:
            self.adapter_calls[channel] += 1
            assert (profile.source_name, profile.environment, profile.host) == (SOURCE, ENV, HOST)
            assert profile.credential_secret_ref == SECRET_REF
            adapter = FakeReadOnlyDemisAdapter(
                rows=[
                    {"encounter_id": "SYN-1"},
                    {"encounter_id": "SYN-2"},
                    {"encounter_id": "SYN-3"},
                ],
                columns=["encounter_id"],
                elapsed_ms=4,
                simulate_timeout=self.timeout,
            )
            self.instances[channel] = adapter
            return adapter

        return core_execute_query(
            session,
            request,
            actor=actor,
            audit_writer=audit_writer,
            eligibility_fn=self.eligibility,
            credential_resolver_factory=resolver_factory,
            adapter_factory=adapter_factory,
        )

    def token(self) -> str:
        eligibility = _eligibility()
        token, _ = issue_execution_token(
            actor=self.actor,
            source_name=eligibility.source_name,
            environment=eligibility.environment,
            template_id=eligibility.template.id,
            version_id=eligibility.version.id,
            catalog_revision_id=eligibility.catalog_revision_id,
            catalog_fingerprint=eligibility.catalog_fingerprint,
            connection_profile_id=eligibility.connection_profile.id,
            connection_profile_fingerprint=connection_profile_binding_fingerprint(
                eligibility.connection_profile
            ),
            parameters=dict(eligibility.resolved_parameters),
            sensitive_parameter_names=list(eligibility.sensitive_parameter_names),
            settings=self.settings,
        )
        return token

    def web(self) -> dict[str, Any]:
        self.active_channel = "web"
        response = web_routes.execute_execution(self.request, Response(), object(), self.actor)
        return response.model_dump(mode="json")

    def mcp(self, token: str) -> dict[str, Any]:
        self.active_channel = "mcp"
        return mcp_adapter.McpApplicationAdapter().execute_query(
            self.actor,
            execution_token=token,
            settings=self.settings,
            session=object(),  # truthy sentinel; DB session not opened
        )


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> OfflineHarness:
    h = OfflineHarness(actor=_actor(), settings=_settings(), request=_request())
    monkeypatch.setattr(web_routes, "execute_query", h.bridge)
    monkeypatch.setattr(mcp_adapter, "execute_query", h.bridge)
    monkeypatch.setattr(mcp_adapter, "evaluate_execution_eligibility", h.eligibility)
    return h


def _normalized(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result.pop("audit_id", None)  # independently generated per execution
    return result


def _audit_contract(events: list[Any], states: list[tuple[str, str]]) -> None:
    assert [(event.event_type, event.status) for event in events] == states
    assert len({event.audit_id for event in events}) == 1
    assert {event.actor_id for event in events} == {"offline-query-operator"}
    assert {event.source_name for event in events} == {SOURCE}
    for event in events:
        assert SENSITIVE not in repr(event)
        assert HOST not in repr(event)
        assert SQL not in repr(event)
        assert SECRET_REF not in repr(event)


def test_web_mcp_shared_core_has_equivalent_rows_caps_and_audit(harness: OfflineHarness) -> None:
    token = harness.token()
    web = harness.web()
    mcp = harness.mcp(token)

    assert _normalized(web) == _normalized(mcp)
    assert (web["row_count"], web["truncated"]) == (2, True)
    assert web["rows"] == [{"encounter_id": "SYN-1"}, {"encounter_id": "SYN-2"}]
    assert (harness.eligibility_calls["web"], harness.eligibility_calls["mcp"]) == (1, 2)
    for channel in ("web", "mcp"):
        _audit_contract(harness.events[channel], AUDIT_OK)
        assert harness.credential_calls[channel] == 1
        assert harness.adapter_calls[channel] == 1
        adapter = harness.instances[channel]
        assert adapter.last_sql_text == SQL
        assert adapter.last_parameters == {"patient_ref": SENSITIVE}
        assert adapter.last_row_limit == 2
        assert adapter.last_timeout_seconds == 3

    for payload in (web, mcp):
        for forbidden in ("sql_text", "host", "credential_secret_ref", "password", SECRET_REF, HOST):
            assert forbidden not in str(payload)


def test_web_mcp_timeout_maps_to_sanitized_errors_and_failed_audit(
    harness: OfflineHarness,
) -> None:
    harness.timeout = True
    token = harness.token()
    with pytest.raises(HTTPException) as web_error:
        harness.web()
    assert web_error.value.status_code == 504
    assert DemisAdapterErrorCode.TIMEOUT in str(web_error.value.detail)

    with pytest.raises(ToolError) as mcp_error:
        harness.mcp(token)
    assert DemisAdapterErrorCode.TIMEOUT in str(mcp_error.value)

    for channel in ("web", "mcp"):
        _audit_contract(
            harness.events[channel],
            [*AUDIT_OK[:3], ("QUERY_EXECUTION", "FAILED")],
        )
        assert harness.events[channel][-1].failure_category == DemisAdapterErrorCode.TIMEOUT
        assert harness.adapter_calls[channel] == 1
        assert harness.credential_calls[channel] == 1
    for value in (web_error.value.detail, str(mcp_error.value)):
        assert SENSITIVE not in str(value)
        assert HOST not in str(value)
        assert SQL not in str(value)


def test_web_mcp_audit_fail_closed_before_adapter_and_secret_resolution(
    harness: OfflineHarness,
) -> None:
    harness.audit_fail = True
    token = harness.token()
    with pytest.raises(HTTPException) as web_error:
        harness.web()
    assert web_error.value.status_code == 503
    assert ExecutionErrorCode.AUDIT_UNAVAILABLE in str(web_error.value.detail)

    with pytest.raises(ToolError) as mcp_error:
        harness.mcp(token)
    assert ExecutionErrorCode.AUDIT_UNAVAILABLE in str(mcp_error.value)

    for channel in ("web", "mcp"):
        assert harness.credential_calls[channel] == 0
        assert harness.adapter_calls[channel] == 0
        assert [(event.event_type, event.status) for event in harness.events[channel]] == AUDIT_OK[:3]


def test_catalog_revision_denial_prevents_web_mcp_execution_and_secret_access(
    harness: OfflineHarness,
) -> None:
    token = harness.token()  # token issued before synthetic revision change
    harness.deny = True
    with pytest.raises(HTTPException) as web_error:
        harness.web()
    assert web_error.value.status_code == 409
    assert ExecutionPreviewErrorCode.CATALOG_MISMATCH in str(web_error.value.detail)

    with pytest.raises(ToolError) as mcp_error:
        harness.mcp(token)
    assert ExecutionPreviewErrorCode.CATALOG_MISMATCH in str(mcp_error.value)

    _audit_contract(
        harness.events["web"],
        [("QUERY_REQUEST", "STARTED"), ("QUERY_REQUEST", "DENIED")],
    )
    assert harness.events["mcp"] == []  # MCP rejected on precheck before shared execute
    for channel in ("web", "mcp"):
        assert harness.credential_calls[channel] == 0
        assert harness.adapter_calls[channel] == 0
