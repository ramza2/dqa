"""Query execution service + durable audit lifecycle tests."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.demis.errors import DemisAdapterError, DemisAdapterErrorCode
from app.adapters.demis.fake import FakeCredentialResolver, FakeReadOnlyDemisAdapter
from app.adapters.demis.profile import ConnectionProfileSnapshot
from app.adapters.execution.errors import ExecutionErrorCode, ExecutionPreviewErrorCode
from app.auth.errors import AuthErrorCode
from app.auth.models import AuthenticatedActor, Role
from app.core.config import get_settings
from app.models.query_audit import QueryAuditEvent
from app.schemas.audit import QueryAuditEventCreate
from app.schemas.query_execution import QueryExecutionRequest
from app.services.catalog_active import activate_catalog_revision
from app.services.catalog_package_import import import_catalog_package_bytes
from app.services.query_audit import record_query_audit_event_durable
from app.services.query_execution import execute_query
from tests.catalog_package_fixtures import (
    DEFAULT_SOURCE,
    build_core_documents,
    build_package_zip,
)

pytestmark = pytest.mark.integration

SOURCE = dict(DEFAULT_SOURCE)
ENVIRONMENT = "dev"
EXECUTE_PATH = "/api/v1/query-executions/execute"
ALLOWED_REF = "env:DEMIS_SECRET_PASSWORD"


def _headers(actor: str, roles: str) -> dict[str, str]:
    return {
        "X-DQA-Dev-Actor": actor,
        "X-DQA-Dev-Roles": roles,
    }


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
        "stable_key": "exec.service.wards",
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


def _approve_enable(db_client: TestClient, template_id: int) -> dict[str, Any]:
    assert (
        db_client.post(
            f"/api/v1/query-templates/{template_id}/submit-review", json={}
        ).status_code
        == 200
    )
    assert (
        db_client.post(
            f"/api/v1/query-templates/{template_id}/approve", json={}
        ).status_code
        == 200
    )
    enabled = db_client.post(f"/api/v1/query-templates/{template_id}/enable")
    assert enabled.status_code == 200
    return enabled.json()


def _ensure_profile(db_client: TestClient, **overrides: Any) -> dict[str, Any]:
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
    created = db_client.post("/api/v1/connection-profiles", json=payload)
    assert created.status_code == 201, created.text
    profile_id = created.json()["id"]
    if enabled:
        enabled_resp = db_client.post(f"/api/v1/connection-profiles/{profile_id}/enable")
        assert enabled_resp.status_code == 200
        return enabled_resp.json()
    return created.json()


def _setup_eligible(
    db_session: Session,
    db_client: TestClient,
    *,
    fingerprint: str = "fp-exec-svc",
    template_overrides: dict[str, Any] | None = None,
    profile_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    revision = _import_and_activate(db_session, fingerprint=fingerprint)
    db_session.commit()
    created = db_client.post(
        "/api/v1/query-templates",
        json=_template_body(**(template_overrides or {})),
    )
    assert created.status_code == 201, created.text
    detail = _approve_enable(db_client, created.json()["id"])
    profile = _ensure_profile(db_client, **(profile_overrides or {}))
    return {
        "revision": revision,
        "template": detail,
        "profile": profile,
        "version_id": detail["version"]["id"],
        "template_id": detail["id"],
        "sql_text": detail["version"]["sql_text"],
    }


def _execute_body(fixture: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "source_name": SOURCE["source_name"],
        "environment": ENVIRONMENT,
        "template_id": fixture["template_id"],
        "version_id": fixture["version_id"],
        "parameters": {"ward_cd": "A01"},
    }
    body.update(overrides)
    return body


def _patch_live_adapter(
    monkeypatch: pytest.MonkeyPatch,
    *,
    rows: list[dict[str, Any]] | None = None,
    simulate_timeout: bool = False,
    simulate_execution_failure: bool = False,
) -> FakeReadOnlyDemisAdapter:
    adapter = FakeReadOnlyDemisAdapter(
        columns=["ward_cd"],
        rows=rows
        or [
            {"ward_cd": "A01"},
            {"ward_cd": "B02"},
            {"ward_cd": "C03"},
        ],
        simulate_timeout=simulate_timeout,
        simulate_execution_failure=simulate_execution_failure,
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


def _audit_rows(db_session: Session, audit_id: str) -> list[QueryAuditEvent]:
    return list(
        db_session.scalars(
            select(QueryAuditEvent)
            .where(QueryAuditEvent.audit_id == audit_id)
            .order_by(QueryAuditEvent.id.asc())
        ).all()
    )


def test_production_execute_fail_closed_without_adapter(
    db_session: Session, db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _setup_eligible(db_session, db_client, fingerprint="fp-prod-deny")
    resolve = MagicMock(side_effect=AssertionError("resolve must not be called"))
    monkeypatch.setattr(
        "app.adapters.demis.env_credentials.EnvironmentCredentialResolver.resolve",
        resolve,
        raising=False,
    )
    monkeypatch.setattr(
        "app.adapters.demis.factory.create_readonly_demis_adapter",
        MagicMock(side_effect=AssertionError("factory must not be called")),
    )

    response = db_client.post(EXECUTE_PATH, json=_execute_body(fixture))
    assert response.status_code == 503
    assert (
        response.json()["detail"]["code"]
        == ExecutionErrorCode.DEMIS_ADAPTER_UNAVAILABLE
    )
    assert "demis.internal.example" not in response.text
    assert ALLOWED_REF not in response.text
    resolve.assert_not_called()

    # Durable DENIED audit survived the HTTP error / request rollback.
    events = list(db_session.scalars(select(QueryAuditEvent)).all())
    assert any(
        e.event_type == "QUERY_REQUEST" and e.status == "STARTED" for e in events
    )
    denied = [
        e
        for e in events
        if e.event_type == "QUERY_REQUEST" and e.status == "DENIED"
    ]
    assert denied
    assert denied[0].failure_category == ExecutionErrorCode.DEMIS_ADAPTER_UNAVAILABLE
    assert "A01" not in str(denied[0].parameter_names)


def test_happy_fake_adapter_execution(
    db_session: Session, db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _setup_eligible(
        db_session,
        db_client,
        fingerprint="fp-happy",
        template_overrides={"row_limit": 2, "timeout_seconds": 9},
    )
    adapter = _patch_live_adapter(monkeypatch)

    response = db_client.post(EXECUTE_PATH, json=_execute_body(fixture))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["row_count"] == 2
    assert body["truncated"] is True
    assert body["elapsed_ms"] == 12
    assert body["columns"] == ["ward_cd"]
    assert body["rows"] == [{"ward_cd": "A01"}, {"ward_cd": "B02"}]
    assert body["connection_profile_id"] == fixture["profile"]["id"]
    assert body["catalog_revision_id"] == fixture["revision"].id
    assert "sql_text" not in body
    assert "host" not in body
    assert response.headers["cache-control"] == "no-store, private"

    assert adapter.last_sql_text == fixture["sql_text"]
    assert adapter.last_parameters == {"ward_cd": "A01", "from_date": "2024-01-01"}
    assert adapter.last_row_limit == 2
    assert adapter.last_timeout_seconds == 9

    events = _audit_rows(db_session, body["audit_id"])
    statuses = [(e.event_type, e.status) for e in events]
    assert statuses == [
        ("QUERY_REQUEST", "STARTED"),
        ("QUERY_REQUEST", "SUCCEEDED"),
        ("QUERY_EXECUTION", "STARTED"),
        ("QUERY_EXECUTION", "SUCCEEDED"),
    ]
    success = events[-1]
    assert success.row_count == 2
    assert success.result_truncated is True
    assert success.elapsed_ms == 12
    assert success.parameter_names == ["ward_cd", "from_date"]
    assert success.sensitive_parameter_names == ["ward_cd"]
    assert "A01" not in str(success.parameter_names)
    assert all(getattr(e, "parameter_logging_policy", None) == "NAMES_ONLY" for e in events)


def test_stale_template_denied_before_adapter(
    db_session: Session, db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _setup_eligible(db_session, db_client, fingerprint="fp-stale")
    stale_version_id = fixture["version_id"]
    newer = db_client.post(
        f"/api/v1/query-templates/{fixture['template_id']}/versions",
        json={},
    )
    assert newer.status_code == 201
    adapter = _patch_live_adapter(monkeypatch)

    response = db_client.post(
        EXECUTE_PATH,
        json=_execute_body(fixture, version_id=stale_version_id),
    )
    assert response.status_code == 409
    assert (
        response.json()["detail"]["code"]
        == ExecutionPreviewErrorCode.STALE_TEMPLATE_VERSION
    )
    assert adapter.last_sql_text is None

    events = list(db_session.scalars(select(QueryAuditEvent)).all())
    denied = [e for e in events if e.status == "DENIED"]
    assert denied
    assert denied[0].failure_category == ExecutionPreviewErrorCode.STALE_TEMPLATE_VERSION


def test_adapter_timeout_and_execution_failure_mapping(
    db_session: Session, db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _setup_eligible(
        db_session,
        db_client,
        fingerprint="fp-timeout",
        template_overrides={"stable_key": "exec.timeout"},
    )
    _patch_live_adapter(monkeypatch, simulate_timeout=True)
    timeout = db_client.post(EXECUTE_PATH, json=_execute_body(fixture))
    assert timeout.status_code == 504
    assert timeout.json()["detail"]["code"] == DemisAdapterErrorCode.TIMEOUT

    timeout_events = [
        e
        for e in db_session.scalars(select(QueryAuditEvent)).all()
        if e.template_id == fixture["template_id"]
        and e.event_type == "QUERY_EXECUTION"
    ]
    assert [(e.status, e.failure_category) for e in timeout_events] == [
        ("STARTED", None),
        ("FAILED", DemisAdapterErrorCode.TIMEOUT),
    ]

    fixture2 = _setup_eligible(
        db_session,
        db_client,
        fingerprint="fp-exec-fail",
        template_overrides={"stable_key": "exec.fail"},
        profile_overrides={"environment": "qa"},
    )
    _patch_live_adapter(monkeypatch, simulate_execution_failure=True)
    failed = db_client.post(
        EXECUTE_PATH,
        json=_execute_body(fixture2, environment="qa"),
    )
    assert failed.status_code == 502
    assert failed.json()["detail"]["code"] == DemisAdapterErrorCode.EXECUTION_FAILED

    fail_events = [
        e
        for e in db_session.scalars(select(QueryAuditEvent)).all()
        if e.template_id == fixture2["template_id"]
        and e.event_type == "QUERY_EXECUTION"
    ]
    assert [(e.status, e.failure_category) for e in fail_events] == [
        ("STARTED", None),
        ("FAILED", DemisAdapterErrorCode.EXECUTION_FAILED),
    ]


def test_resolver_failure_execution_started_then_failed(
    db_session: Session, db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _setup_eligible(db_session, db_client, fingerprint="fp-resolver-fail")
    monkeypatch.setattr(
        "app.services.execution_eligibility.is_concrete_demis_adapter_available",
        lambda dbms_type: True,
    )
    factory_calls: list[str] = []

    def _resolver_boom(settings=None):
        factory_calls.append("resolver")
        raise DemisAdapterError(
            DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE,
            "credential material is unavailable",
        )

    def _adapter_boom(profile, credential_resolver):
        factory_calls.append("adapter")
        raise AssertionError("adapter must not be built when resolver fails")

    monkeypatch.setattr(
        "app.adapters.demis.credential_factory.create_credential_resolver",
        _resolver_boom,
    )
    monkeypatch.setattr(
        "app.services.query_execution.create_readonly_demis_adapter",
        _adapter_boom,
    )

    response = db_client.post(EXECUTE_PATH, json=_execute_body(fixture))
    assert response.status_code == 503
    assert (
        response.json()["detail"]["code"]
        == DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE
    )
    assert "ValidationError" not in response.text
    assert factory_calls == ["resolver"]

    events = [
        e
        for e in db_session.scalars(select(QueryAuditEvent)).all()
        if e.template_id == fixture["template_id"]
    ]
    statuses = [(e.event_type, e.status, e.failure_category) for e in events]
    assert statuses == [
        ("QUERY_REQUEST", "STARTED", None),
        ("QUERY_REQUEST", "SUCCEEDED", None),
        ("QUERY_EXECUTION", "STARTED", None),
        (
            "QUERY_EXECUTION",
            "FAILED",
            DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE,
        ),
    ]


def test_adapter_factory_failure_execution_started_then_failed(
    db_session: Session, db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _setup_eligible(db_session, db_client, fingerprint="fp-factory-fail")
    monkeypatch.setattr(
        "app.services.execution_eligibility.is_concrete_demis_adapter_available",
        lambda dbms_type: True,
    )
    monkeypatch.setattr(
        "app.adapters.demis.credential_factory.create_credential_resolver",
        lambda settings=None: FakeCredentialResolver(
            {ALLOWED_REF: "test-secret-value"}
        ),
    )

    def _factory_boom(profile, credential_resolver):
        raise DemisAdapterError(
            DemisAdapterErrorCode.UNSUPPORTED_DBMS,
            "no concrete DEMIS adapter is registered",
        )

    monkeypatch.setattr(
        "app.services.query_execution.create_readonly_demis_adapter",
        _factory_boom,
    )

    response = db_client.post(EXECUTE_PATH, json=_execute_body(fixture))
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == DemisAdapterErrorCode.UNSUPPORTED_DBMS

    events = [
        e
        for e in db_session.scalars(select(QueryAuditEvent)).all()
        if e.template_id == fixture["template_id"]
        and e.event_type == "QUERY_EXECUTION"
    ]
    assert [(e.status, e.failure_category) for e in events] == [
        ("STARTED", None),
        ("FAILED", DemisAdapterErrorCode.UNSUPPORTED_DBMS),
    ]


def test_oversized_approved_sql_rejected_before_adapter(
    db_session: Session, db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.adapters.demis.types import MAX_SQL_TEXT_LENGTH
    from app.models.query_template import QueryTemplateVersion

    fixture = _setup_eligible(db_session, db_client, fingerprint="fp-sql-too-long")
    version = db_session.get(QueryTemplateVersion, fixture["version_id"])
    assert version is not None
    # Keep a SELECT prefix so any accidental safety path stays deterministic;
    # length gate must reject before credential/adapter access.
    version.sql_text = "SELECT 1 FROM dual WHERE 1=1 -- " + (
        "x" * (MAX_SQL_TEXT_LENGTH + 1)
    )
    db_session.commit()

    resolve = MagicMock(side_effect=AssertionError("resolve must not be called"))
    monkeypatch.setattr(
        "app.services.execution_eligibility.is_concrete_demis_adapter_available",
        lambda dbms_type: True,
    )
    monkeypatch.setattr(
        "app.adapters.demis.credential_factory.create_credential_resolver",
        MagicMock(
            side_effect=AssertionError("credential resolver must not be created")
        ),
    )
    monkeypatch.setattr(
        "app.services.query_execution.create_readonly_demis_adapter",
        MagicMock(side_effect=AssertionError("adapter factory must not be called")),
    )
    monkeypatch.setattr(
        "app.adapters.demis.env_credentials.EnvironmentCredentialResolver.resolve",
        resolve,
        raising=False,
    )

    response = db_client.post(EXECUTE_PATH, json=_execute_body(fixture))
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == ExecutionPreviewErrorCode.TEMPLATE_NOT_ELIGIBLE
    assert "ValidationError" not in response.text
    assert "SELECT 1 FROM dual" not in response.text
    assert "xxxxx" not in response.text
    resolve.assert_not_called()

    events = [
        e
        for e in db_session.scalars(select(QueryAuditEvent)).all()
        if e.template_id == fixture["template_id"]
    ]
    assert [(e.event_type, e.status) for e in events] == [
        ("QUERY_REQUEST", "STARTED"),
        ("QUERY_REQUEST", "DENIED"),
    ]
    assert events[-1].failure_category == ExecutionPreviewErrorCode.TEMPLATE_NOT_ELIGIBLE


def test_readonly_request_validation_failure_sanitized(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unexpected ReadonlyQueryRequest validation must not leak as 500/Pydantic."""
    from pydantic import ValidationError

    writes: list[QueryAuditEventCreate] = []

    def _writer(payload: QueryAuditEventCreate):
        writes.append(payload)
        return record_query_audit_event_durable(payload)

    eligibility = MagicMock()
    eligibility.execution_available = True
    eligibility.execution_blockers = []
    eligibility.source_name = SOURCE["source_name"]
    eligibility.environment = ENVIRONMENT
    eligibility.catalog_revision_id = 1
    eligibility.catalog_fingerprint = "fp"
    eligibility.template = MagicMock()
    eligibility.template.id = 11
    eligibility.version = MagicMock()
    eligibility.version.id = 22
    eligibility.version.version = 1
    # Empty sql_text would fail ReadonlyQueryRequest; eligibility should normally
    # prevent this — defensive path still must sanitize.
    eligibility.version.sql_text = "   "
    eligibility.connection_profile = MagicMock()
    eligibility.connection_profile.id = 33
    eligibility.connection_profile.name = "p"
    eligibility.connection_profile.source_name = SOURCE["source_name"]
    eligibility.connection_profile.environment = ENVIRONMENT
    eligibility.connection_profile.enabled = True
    eligibility.connection_profile.dbms_type = "oracle"
    eligibility.connection_profile.host = "h"
    eligibility.connection_profile.port = 1
    eligibility.connection_profile.database_name = "d"
    eligibility.connection_profile.username = "u"
    eligibility.connection_profile.credential_secret_ref = ALLOWED_REF
    eligibility.parameters = []
    eligibility.resolved_parameters = {"secret_param": "SECRET_VALUE"}
    eligibility.sensitive_parameter_names = []
    eligibility.row_limit = 10
    eligibility.timeout_seconds = 5

    actor = AuthenticatedActor(
        actor_id="op",
        roles=frozenset({Role.QUERY_OPERATOR}),
        provider="dev_headers",
    )
    adapter = FakeReadOnlyDemisAdapter(columns=["c"], rows=[{"c": 1}])

    with pytest.raises(DemisAdapterError) as exc:
        execute_query(
            db_session,
            QueryExecutionRequest.model_validate(
                {
                    "source_name": SOURCE["source_name"],
                    "environment": ENVIRONMENT,
                    "template_id": 11,
                    "version_id": 22,
                    "parameters": {},
                }
            ),
            actor=actor,
            audit_writer=_writer,
            eligibility_fn=lambda *a, **k: eligibility,
            credential_resolver_factory=lambda: FakeCredentialResolver(
                {ALLOWED_REF: "x"}
            ),
            adapter_factory=lambda profile, credential_resolver: adapter,
        )
    assert exc.value.code == DemisAdapterErrorCode.EXECUTION_FAILED
    assert "SECRET_VALUE" not in str(exc.value)
    assert "ValidationError" not in str(exc.value)
    assert not isinstance(exc.value.__cause__, ValidationError)
    assert adapter.last_sql_text is None
    statuses = [(w.event_type, w.status) for w in writes]
    assert statuses == [
        ("QUERY_REQUEST", "STARTED"),
        ("QUERY_REQUEST", "SUCCEEDED"),
        ("QUERY_EXECUTION", "STARTED"),
        ("QUERY_EXECUTION", "FAILED"),
    ]
    assert writes[-1].failure_category == DemisAdapterErrorCode.EXECUTION_FAILED


def test_execution_started_audit_failure_blocks_credentials(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    writes: list[QueryAuditEventCreate] = []
    resolver_called = MagicMock()

    def _writer(payload: QueryAuditEventCreate):
        writes.append(payload)
        if (
            payload.event_type == "QUERY_EXECUTION"
            and payload.status == "STARTED"
        ):
            raise RuntimeError("execution started audit down")
        return record_query_audit_event_durable(payload)

    eligibility = MagicMock()
    eligibility.execution_available = True
    eligibility.execution_blockers = []
    eligibility.source_name = SOURCE["source_name"]
    eligibility.environment = ENVIRONMENT
    eligibility.catalog_revision_id = 1
    eligibility.catalog_fingerprint = "fp"
    eligibility.template = MagicMock()
    eligibility.template.id = 1
    eligibility.version = MagicMock()
    eligibility.version.id = 2
    eligibility.version.version = 1
    eligibility.version.sql_text = "SELECT 1 FROM dual"
    eligibility.connection_profile = MagicMock()
    eligibility.connection_profile.id = 3
    eligibility.connection_profile.name = "p"
    eligibility.connection_profile.source_name = SOURCE["source_name"]
    eligibility.connection_profile.environment = ENVIRONMENT
    eligibility.connection_profile.enabled = True
    eligibility.connection_profile.dbms_type = "oracle"
    eligibility.connection_profile.host = "h"
    eligibility.connection_profile.port = 1
    eligibility.connection_profile.database_name = "d"
    eligibility.connection_profile.username = "u"
    eligibility.connection_profile.credential_secret_ref = ALLOWED_REF
    eligibility.parameters = []
    eligibility.resolved_parameters = {}
    eligibility.sensitive_parameter_names = []
    eligibility.row_limit = 10
    eligibility.timeout_seconds = 5

    actor = AuthenticatedActor(
        actor_id="op",
        roles=frozenset({Role.QUERY_OPERATOR}),
        provider="dev_headers",
    )
    with pytest.raises(Exception) as exc:
        execute_query(
            db_session,
            QueryExecutionRequest.model_validate(
                {
                    "source_name": SOURCE["source_name"],
                    "environment": ENVIRONMENT,
                    "template_id": 1,
                    "version_id": 2,
                    "parameters": {},
                }
            ),
            actor=actor,
            audit_writer=_writer,
            eligibility_fn=lambda *a, **k: eligibility,
            credential_resolver_factory=lambda: resolver_called()
            or FakeCredentialResolver({ALLOWED_REF: "x"}),
            adapter_factory=lambda profile, credential_resolver: (
                FakeReadOnlyDemisAdapter(columns=["c"], rows=[])
            ),
        )
    assert getattr(exc.value, "code", None) == ExecutionErrorCode.AUDIT_UNAVAILABLE
    resolver_called.assert_not_called()
    assert "audit down" not in str(exc.value)


def test_initial_audit_failure_prevents_adapter(
    db_session: Session, db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _setup_eligible(db_session, db_client, fingerprint="fp-audit-start")
    adapter = _patch_live_adapter(monkeypatch)

    def _boom(payload: QueryAuditEventCreate):
        raise RuntimeError("audit db down")

    monkeypatch.setattr(
        "app.services.query_execution.record_query_audit_event_durable",
        _boom,
    )
    response = db_client.post(EXECUTE_PATH, json=_execute_body(fixture))
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == ExecutionErrorCode.AUDIT_UNAVAILABLE
    assert adapter.last_sql_text is None
    assert "audit db down" not in response.text


def test_final_audit_failure_suppresses_result_rows(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Service-level: after adapter success, final SUCCEEDED audit fails.
    adapter = FakeReadOnlyDemisAdapter(
        columns=["ward_cd"],
        rows=[{"ward_cd": "SECRET_ROW"}],
        elapsed_ms=3,
    )
    writes: list[QueryAuditEventCreate] = []

    def _writer(payload: QueryAuditEventCreate):
        writes.append(payload)
        if (
            payload.event_type == "QUERY_EXECUTION"
            and payload.status == "SUCCEEDED"
        ):
            raise RuntimeError("final audit failed")
        return record_query_audit_event_durable(payload)

    eligibility = MagicMock()
    eligibility.execution_available = True
    eligibility.execution_blockers = []
    eligibility.source_name = SOURCE["source_name"]
    eligibility.environment = ENVIRONMENT
    eligibility.catalog_revision_id = 1
    eligibility.catalog_fingerprint = "fp"
    eligibility.template = MagicMock()
    eligibility.template.id = 1
    eligibility.version = MagicMock()
    eligibility.version.id = 2
    eligibility.version.version = 1
    eligibility.version.sql_text = "SELECT 1 FROM dual"
    eligibility.connection_profile = MagicMock()
    eligibility.connection_profile.id = 3
    eligibility.connection_profile.name = "p"
    eligibility.connection_profile.source_name = SOURCE["source_name"]
    eligibility.connection_profile.environment = ENVIRONMENT
    eligibility.connection_profile.enabled = True
    eligibility.connection_profile.dbms_type = "oracle"
    eligibility.connection_profile.host = "h"
    eligibility.connection_profile.port = 1
    eligibility.connection_profile.database_name = "d"
    eligibility.connection_profile.username = "u"
    eligibility.connection_profile.credential_secret_ref = ALLOWED_REF
    eligibility.parameters = []
    eligibility.resolved_parameters = {}
    eligibility.sensitive_parameter_names = []
    eligibility.row_limit = 10
    eligibility.timeout_seconds = 5

    actor = AuthenticatedActor(
        actor_id="op",
        roles=frozenset({Role.QUERY_OPERATOR}),
        provider="dev_headers",
    )
    with pytest.raises(Exception) as exc:
        execute_query(
            db_session,
            QueryExecutionRequest.model_validate(
                {
                    "source_name": SOURCE["source_name"],
                    "environment": ENVIRONMENT,
                    "template_id": 1,
                    "version_id": 2,
                    "parameters": {},
                }
            ),
            actor=actor,
            audit_writer=_writer,
            eligibility_fn=lambda *a, **k: eligibility,
            credential_resolver_factory=lambda: FakeCredentialResolver(
                {ALLOWED_REF: "x"}
            ),
            adapter_factory=lambda profile, credential_resolver: adapter,
        )
    assert getattr(exc.value, "code", None) == ExecutionErrorCode.AUDIT_UNAVAILABLE
    assert "SECRET_ROW" not in str(exc.value)
    assert any(
        w.event_type == "QUERY_EXECUTION" and w.status == "SUCCEEDED" for w in writes
    )


def test_durable_audit_survives_request_error_rollback(
    db_session: Session, db_client: TestClient
) -> None:
    fixture = _setup_eligible(db_session, db_client, fingerprint="fp-durable")
    response = db_client.post(EXECUTE_PATH, json=_execute_body(fixture))
    assert response.status_code == 503
    # Request dependency rolled back, but durable writer committed.
    db_session.expire_all()
    events = list(db_session.scalars(select(QueryAuditEvent)).all())
    assert len(events) >= 2
    assert {e.status for e in events} >= {"STARTED", "DENIED"}


def test_rows_not_logged(
    db_session: Session,
    db_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fixture = _setup_eligible(db_session, db_client, fingerprint="fp-nolog")
    _patch_live_adapter(
        monkeypatch,
        rows=[{"ward_cd": "SENSITIVE_WARD"}],
    )
    with caplog.at_level(logging.DEBUG):
        response = db_client.post(EXECUTE_PATH, json=_execute_body(fixture))
        logging.getLogger("test.execute").info(
            "status=%s audit_id=%s",
            response.status_code,
            response.json().get("audit_id"),
        )
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "SENSITIVE_WARD" not in joined
    assert "demis.internal.example" not in joined
    assert "SELECT ward_cd" not in joined
    assert ALLOWED_REF not in joined
    assert response.status_code == 200


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("query_operator", 503),  # production fail-closed: no concrete adapter
        ("administrator", 503),
        ("viewer", 403),
        ("auditor", 403),
    ],
)
def test_execute_rbac(
    db_session: Session,
    db_client: TestClient,
    unauth_db_client: TestClient,
    role: str,
    expected: int,
) -> None:
    fixture = _setup_eligible(
        db_session,
        db_client,
        fingerprint=f"fp-rbac-exec-{role}",
        template_overrides={"stable_key": f"exec.rbac.{role}"},
    )
    response = unauth_db_client.post(
        EXECUTE_PATH,
        json=_execute_body(fixture),
        headers=_headers(f"user-{role}", role),
    )
    assert response.status_code == expected
    if expected == 403:
        assert response.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED


def test_missing_identity_401(unauth_db_client: TestClient) -> None:
    response = unauth_db_client.post(
        EXECUTE_PATH,
        json={
            "source_name": "x",
            "environment": "dev",
            "template_id": 1,
            "version_id": 1,
            "parameters": {},
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == AuthErrorCode.AUTHENTICATION_REQUIRED


def test_provider_disabled_503(
    monkeypatch: pytest.MonkeyPatch, test_settings_env: dict[str, str]
) -> None:
    monkeypatch.setenv("DQA_AUTH_PROVIDER", "disabled")
    from app.adapters.db.session import get_engine, get_session_factory
    from app.main import create_app

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    application = create_app(init_db_on_startup=False)
    with TestClient(application) as client:
        response = client.post(
            EXECUTE_PATH,
            json={
                "source_name": "x",
                "environment": "dev",
                "template_id": 1,
                "version_id": 1,
                "parameters": {},
            },
            headers=_headers("op", "query_operator"),
        )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == AuthErrorCode.PROVIDER_NOT_CONFIGURED
    get_settings.cache_clear()


def test_production_cannot_select_fake_via_profile_dbms(
    db_session: Session, db_client: TestClient
) -> None:
    fixture = _setup_eligible(
        db_session,
        db_client,
        fingerprint="fp-fake-dbms",
        template_overrides={"stable_key": "exec.fake.dbms"},
        profile_overrides={"dbms_type": "fake", "environment": "fake-env"},
    )
    response = db_client.post(
        EXECUTE_PATH,
        json=_execute_body(fixture, environment="fake-env"),
    )
    # eligibility marks adapter unavailable (fake kinds never available)
    assert response.status_code == 503
    assert (
        response.json()["detail"]["code"]
        == ExecutionErrorCode.DEMIS_ADAPTER_UNAVAILABLE
    )


def test_response_repr_omits_rows() -> None:
    from app.schemas.query_execution import QueryExecutionResponse

    payload = QueryExecutionResponse(
        audit_id="a",
        source_name="s",
        environment="dev",
        catalog_revision_id=1,
        catalog_fingerprint="fp",
        template_id=1,
        version_id=1,
        version=1,
        connection_profile_id=1,
        columns=["ward_cd"],
        rows=[{"ward_cd": "SECRET"}],
        row_count=1,
        truncated=False,
        elapsed_ms=1,
    )
    assert "SECRET" not in repr(payload)
