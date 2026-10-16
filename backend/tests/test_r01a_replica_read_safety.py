"""R-01-A: replica-read target isolation / fail-closed regression, pure synthetic.

No db_session, live socket/Oracle, production endpoints, credentials or patient data.
These tests pin CURRENT read-only behavior; site replica access remains DEC-10 blocked.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.adapters.demis.credentials import CredentialMaterial
from app.adapters.demis.errors import DemisAdapterError, DemisAdapterErrorCode
from app.adapters.demis.factory import create_readonly_demis_adapter
from app.adapters.demis.oracle import OracleReadOnlyDemisAdapter
from app.adapters.demis.profile import ConnectionProfileSnapshot
from app.adapters.demis.types import ReadonlyQueryRequest
from app.adapters.execution.errors import ExecutionPreviewError, ExecutionPreviewErrorCode
from app.auth.models import AuthenticatedActor, Role
from app.schemas.query_execution import QueryExecutionRequest
from app.services import execution_eligibility
from app.services.execution_eligibility import (
    ExecutionEligibilityResult, _require_eligible_connection_profile,
)
from app.services.query_execution import execute_query

SOURCE = "replicated_emr_synthetic"
OTHER_SOURCE = "operational_emr_synthetic"
ENV = "sandbox"
REPLICA_HOST = "replica.invalid"
ORIGINAL_HOST = "original.invalid"
SECRET_REF = "env:DEMIS_SECRET_SYNTHETIC"
SENSITIVE = "synthetic-credential-do-not-share"


def _profile(**changes: Any) -> ConnectionProfileSnapshot:
    values = {
        "profile_id": 41, "name": "Synthetic replica read source",
        "source_name": SOURCE, "environment": ENV, "enabled": True,
        "dbms_type": "oracle", "host": REPLICA_HOST, "port": 1521,
        "database_name": "MOCK_ONLY", "username": "mock_reader",
        "credential_secret_ref": SECRET_REF,
    }
    values.update(changes)
    return ConnectionProfileSnapshot.model_validate(values)


def _credential() -> CredentialMaterial:
    return CredentialMaterial(secret_ref=SECRET_REF, _secret=SENSITIVE)


def _request() -> ReadonlyQueryRequest:
    return ReadonlyQueryRequest(
        sql_text="SELECT record_id FROM synthetic_records WHERE record_id = :record_id",
        parameters={"record_id": "SYN-001"}, timeout_seconds=3, row_limit=2,
    )


@pytest.mark.parametrize("dbms", ["postgresql", "mysql", "sqlite", "unknown", "fake"])
def test_unsupported_replica_dbms_never_resolves_secret_or_falls_back(dbms: str) -> None:
    resolver = Mock()
    with pytest.raises(DemisAdapterError) as err:
        create_readonly_demis_adapter(
            _profile(dbms_type=dbms), credential_resolver=resolver,
        )
    assert err.value.code == DemisAdapterErrorCode.UNSUPPORTED_DBMS
    resolver.resolve.assert_not_called()


@pytest.mark.parametrize("operation", ["execute", "probe"])
def test_replica_connection_failure_makes_one_attempt_without_original_fallback(
    operation: str,
) -> None:
    attempts: list[str] = []

    def failed_connect(**kwargs: Any) -> Any:
        attempts.append(kwargs["host"])
        raise OSError("synthetic transport failure")

    adapter = OracleReadOnlyDemisAdapter(
        profile=_profile(), credential=_credential(), connect=failed_connect,
    )
    with pytest.raises(DemisAdapterError) as err:
        if operation == "execute":
            adapter.execute_readonly(_request())
        else:
            adapter.probe_readonly()
    assert err.value.code == DemisAdapterErrorCode.CONNECTION_FAILED
    assert attempts == [REPLICA_HOST]
    for forbidden in [REPLICA_HOST, ORIGINAL_HOST, SENSITIVE, SECRET_REF]:
        assert forbidden not in str(err.value)
        assert forbidden not in repr(err.value)
    assert err.value.__cause__ is None


def test_readonly_transaction_failure_stops_before_any_application_select() -> None:
    calls: list[str] = []
    closed: list[str] = []

    class Cursor:
        def execute(self, sql: str, params: Any = None) -> None:
            calls.append(sql)
            raise RuntimeError("synthetic cannot set READ ONLY")

        def close(self) -> None:
            closed.append("cursor")

    class Connection:
        autocommit = True
        call_timeout = 0

        def cursor(self) -> Cursor:
            return Cursor()

        def rollback(self) -> None:
            closed.append("rollback")

        def close(self) -> None:
            closed.append("connection")

    attempts: list[str] = []

    def connect(**kwargs: Any) -> Connection:
        attempts.append(kwargs["host"])
        return Connection()

    adapter = OracleReadOnlyDemisAdapter(
        profile=_profile(), credential=_credential(), connect=connect,
    )
    with pytest.raises(DemisAdapterError) as err:
        adapter.execute_readonly(_request())
    assert err.value.code == DemisAdapterErrorCode.EXECUTION_FAILED
    assert attempts == [REPLICA_HOST]
    assert calls == ["SET TRANSACTION READ ONLY"]
    assert closed == ["cursor", "rollback", "connection"]


@pytest.mark.parametrize("returned", [
    None,
    SimpleNamespace(source_name=OTHER_SOURCE, environment=ENV, enabled=True),
    SimpleNamespace(source_name=SOURCE, environment="other", enabled=True),
])
def test_profile_lookup_is_exact_source_environment_and_never_searches_other(
    monkeypatch: pytest.MonkeyPatch, returned: Any,
) -> None:
    looked_up: list[tuple[str, str]] = []

    class Repository:
        def get_by_source_and_environment(self, source: str, env: str) -> Any:
            looked_up.append((source, env))
            return returned

    monkeypatch.setattr(
        execution_eligibility, "ConnectionProfileRepository", lambda _: Repository(),
    )
    with pytest.raises(ExecutionPreviewError) as err:
        _require_eligible_connection_profile(None, source_name=SOURCE, environment=ENV)
    assert err.value.code == ExecutionPreviewErrorCode.CONNECTION_PROFILE_NOT_FOUND
    assert looked_up == [(SOURCE, ENV)]


@pytest.mark.parametrize("override", [
    {"host": ORIGINAL_HOST}, {"dbms_type": "postgresql"},
    {"connection_profile_id": 1}, {"database_name": "ORIGINAL"},
])
def test_operator_cannot_override_replica_physical_target(override: dict[str, Any]) -> None:
    payload = {
        "source_name": SOURCE, "environment": ENV,
        "template_id": 11, "version_id": 12, "parameters": {},
    }
    with pytest.raises(ValidationError):
        QueryExecutionRequest.model_validate({**payload, **override})


def _eligibility() -> ExecutionEligibilityResult:
    profile = SimpleNamespace(
        id=41, name="Synthetic replica", source_name=SOURCE,
        environment=ENV, enabled=True, dbms_type="oracle",
        host=REPLICA_HOST, port=1521, database_name="MOCK_ONLY",
        username="mock_reader", credential_secret_ref=SECRET_REF,
    )
    return ExecutionEligibilityResult(
        source_name=SOURCE, environment=ENV,
        template=SimpleNamespace(id=11),
        version=SimpleNamespace(
            id=12, version=1, sql_text=_request().sql_text,
        ),
        catalog_revision_id=51, catalog_fingerprint="synthetic-only",
        connection_profile=profile, parameters=[],
        resolved_parameters={"record_id": "SYN-001"},
        sensitive_parameter_names=[], row_limit=2, timeout_seconds=3,
        execution_available=True,
    )


@pytest.mark.parametrize("failure_phase", ["factory", "execution"])
def test_query_service_failure_does_not_retry_other_target_and_audits(
    failure_phase: str,
) -> None:
    factory_profiles: list[ConnectionProfileSnapshot] = []
    resolver_calls: list[int] = []
    adapter_calls: list[ReadonlyQueryRequest] = []
    audit_events: list[Any] = []

    def resolver_factory() -> object:
        resolver_calls.append(1)
        return object()

    class FailingAdapter:
        def execute_readonly(self, req: ReadonlyQueryRequest) -> None:
            adapter_calls.append(req)
            raise DemisAdapterError(
                DemisAdapterErrorCode.CONNECTION_FAILED, "synthetic target offline",
            )

    def adapter_factory(profile: ConnectionProfileSnapshot, *, credential_resolver: Any) -> Any:
        factory_profiles.append(profile)
        if failure_phase == "factory":
            raise DemisAdapterError(
                DemisAdapterErrorCode.CONNECTION_FAILED, "synthetic target offline",
            )
        return FailingAdapter()

    def audit_writer(event: Any) -> None:
        audit_events.append(event)

    actor = AuthenticatedActor(
        actor_id="synthetic-operator", roles=frozenset({Role.QUERY_OPERATOR}), provider="test",
    )
    request = QueryExecutionRequest(
        source_name=SOURCE, environment=ENV, template_id=11,
        version_id=12, parameters={"record_id": "SYN-001"},
    )
    with pytest.raises(DemisAdapterError) as err:
        execute_query(
            None, request, actor=actor,
            audit_writer=audit_writer,
            eligibility_fn=lambda *args, **kwargs: _eligibility(),
            credential_resolver_factory=resolver_factory,
            adapter_factory=adapter_factory,
        )
    assert err.value.code == DemisAdapterErrorCode.CONNECTION_FAILED
    assert len(resolver_calls) == 1
    assert [(p.source_name, p.environment, p.host) for p in factory_profiles] == [
        (SOURCE, ENV, REPLICA_HOST),
    ]
    assert len(adapter_calls) == (0 if failure_phase == "factory" else 1)
    assert [(e.event_type, e.status) for e in audit_events] == [
        ("QUERY_REQUEST", "STARTED"),
        ("QUERY_REQUEST", "SUCCEEDED"),
        ("QUERY_EXECUTION", "STARTED"),
        ("QUERY_EXECUTION", "FAILED"),
    ]
    assert audit_events[-1].failure_category == DemisAdapterErrorCode.CONNECTION_FAILED
    assert audit_events[-1].source_name == SOURCE
    assert all(e.source_name == SOURCE for e in audit_events)


def test_query_service_denies_wrong_source_before_resolving_any_credential() -> None:
    audit_events: list[Any] = []
    resolver = Mock(side_effect=AssertionError("credential resolution forbidden"))
    factory = Mock(side_effect=AssertionError("adapter creation forbidden"))
    actor = AuthenticatedActor(
        actor_id="synthetic-operator", roles=frozenset({Role.QUERY_OPERATOR}), provider="test",
    )

    def deny(*args: Any, **kwargs: Any) -> Any:
        assert kwargs["source_name"] == SOURCE and kwargs["environment"] == ENV
        raise ExecutionPreviewError(
            ExecutionPreviewErrorCode.CONNECTION_PROFILE_NOT_FOUND,
            "connection profile not found for source and environment",
        )

    with pytest.raises(ExecutionPreviewError) as err:
        execute_query(
            None, QueryExecutionRequest(
                source_name=SOURCE, environment=ENV, template_id=11,
                version_id=12, parameters={},
            ),
            actor=actor,
            audit_writer=lambda event: audit_events.append(event),
            eligibility_fn=deny,
            credential_resolver_factory=resolver,
            adapter_factory=factory,
        )
    assert err.value.code == ExecutionPreviewErrorCode.CONNECTION_PROFILE_NOT_FOUND
    resolver.assert_not_called()
    factory.assert_not_called()
    assert [(e.event_type, e.status) for e in audit_events] == [
        ("QUERY_REQUEST", "STARTED"), ("QUERY_REQUEST", "DENIED"),
    ]
