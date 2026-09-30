"""DEMIS read-only adapter foundation contract tests."""

from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError

from app.adapters.demis import (
    ConnectionProfileSnapshot,
    DemisAdapterDiagnostics,
    DemisAdapterError,
    DemisAdapterErrorCode,
    ReadonlyQueryRequest,
    ReadonlyQueryResult,
    create_readonly_demis_adapter,
)
from app.adapters.demis.fake import (
    FakeCredentialResolver,
    FakeReadOnlyDemisAdapter,
    build_fake_readonly_demis_adapter,
)
from app.api.routes import api_router


def _eligible_snapshot(**overrides: object) -> ConnectionProfileSnapshot:
    body: dict[str, object] = {
        "profile_id": 1,
        "name": "Mock DEMIS profile",
        "source_name": "oracle_demis_mock",
        "environment": "dev",
        "enabled": True,
        "dbms_type": "oracle",
        "host": "demis.internal.example",
        "port": 1521,
        "database_name": "DEMIS",
        "username": "dqa_ro",
        "credential_secret_ref": "env:DEMIS_DB_PASSWORD",
    }
    body.update(overrides)
    return ConnectionProfileSnapshot.model_validate(body)


def _resolver() -> FakeCredentialResolver:
    return FakeCredentialResolver({"env:DEMIS_DB_PASSWORD": "test-secret-value"})


def test_readonly_request_contract_bounds() -> None:
    ok = ReadonlyQueryRequest(
        sql_text="SELECT ward_cd FROM wards WHERE ward_cd = :ward_cd",
        parameters={"ward_cd": "A01"},
        timeout_seconds=15,
        row_limit=50,
    )
    assert ok.row_limit == 50

    with pytest.raises(ValidationError):
        ReadonlyQueryRequest(
            sql_text="SELECT 1",
            parameters={},
            timeout_seconds=0,
            row_limit=10,
        )
    with pytest.raises(ValidationError):
        ReadonlyQueryRequest(
            sql_text="SELECT 1",
            parameters={},
            timeout_seconds=10,
            row_limit=0,
        )
    with pytest.raises(ValidationError):
        ReadonlyQueryRequest(
            sql_text="   ",
            parameters={},
            timeout_seconds=10,
            row_limit=10,
        )


def test_fake_adapter_keeps_bound_parameters_separate() -> None:
    adapter = build_fake_readonly_demis_adapter(
        columns=["ward_cd", "ward_nm"],
        rows=[
            {"ward_cd": "A01", "ward_nm": "Ward A"},
            {"ward_cd": "B02", "ward_nm": "Ward B"},
            {"ward_cd": "C03", "ward_nm": "Ward C"},
        ],
    )
    sql = "SELECT ward_cd, ward_nm FROM wards WHERE ward_cd = :ward_cd"
    result = adapter.execute_readonly(
        ReadonlyQueryRequest(
            sql_text=sql,
            parameters={"ward_cd": "A01"},
            timeout_seconds=5,
            row_limit=2,
        )
    )
    assert adapter.last_sql_text == sql
    assert adapter.last_parameters == {"ward_cd": "A01"}
    assert "A01" not in (adapter.last_sql_text or "")
    assert result.row_count == 2
    assert result.truncated is True
    assert result.columns == ["ward_cd", "ward_nm"]
    assert result.rows[0]["ward_cd"] == "A01"


def test_fake_adapter_timeout_and_execution_failure_categories() -> None:
    timeout_adapter = FakeReadOnlyDemisAdapter(simulate_timeout=True)
    with pytest.raises(DemisAdapterError) as timeout_exc:
        timeout_adapter.execute_readonly(
            ReadonlyQueryRequest(
                sql_text="SELECT 1",
                parameters={},
                timeout_seconds=1,
                row_limit=10,
            )
        )
    assert timeout_exc.value.failure_category == DemisAdapterErrorCode.TIMEOUT

    fail_adapter = FakeReadOnlyDemisAdapter(simulate_execution_failure=True)
    with pytest.raises(DemisAdapterError) as fail_exc:
        fail_adapter.execute_readonly(
            ReadonlyQueryRequest(
                sql_text="SELECT 1",
                parameters={},
                timeout_seconds=1,
                row_limit=10,
            )
        )
    assert fail_exc.value.failure_category == DemisAdapterErrorCode.EXECUTION_FAILED


def test_disabled_profile_rejected() -> None:
    with pytest.raises(DemisAdapterError) as exc:
        create_readonly_demis_adapter(
            _eligible_snapshot(enabled=False),
            credential_resolver=_resolver(),
        )
    assert exc.value.code == DemisAdapterErrorCode.PROFILE_DISABLED
    assert "demis.internal.example" not in str(exc.value)
    assert "dqa_ro" not in str(exc.value)
    assert "test-secret-value" not in str(exc.value)


def test_missing_credential_reference_rejected() -> None:
    resolver = _TrackingCredentialResolver({"env:DEMIS_DB_PASSWORD": "test-secret-value"})
    with pytest.raises(DemisAdapterError) as exc:
        create_readonly_demis_adapter(
            _eligible_snapshot(credential_secret_ref=None),
            credential_resolver=resolver,
        )
    assert exc.value.code == DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE
    assert resolver.resolve_calls == []


def test_incomplete_target_metadata_rejected() -> None:
    resolver = _TrackingCredentialResolver({"env:DEMIS_DB_PASSWORD": "test-secret-value"})
    with pytest.raises(DemisAdapterError) as exc:
        create_readonly_demis_adapter(
            _eligible_snapshot(host=None, port=None),
            credential_resolver=resolver,
        )
    assert exc.value.code == DemisAdapterErrorCode.ADAPTER_NOT_CONFIGURED
    assert "demis.internal.example" not in str(exc.value)
    assert resolver.resolve_calls == []


def test_unsupported_dbms_does_not_resolve_credentials() -> None:
    resolver = _TrackingCredentialResolver({"env:DEMIS_DB_PASSWORD": "test-secret-value"})
    with pytest.raises(DemisAdapterError) as exc:
        create_readonly_demis_adapter(
            _eligible_snapshot(dbms_type="oracle"),
            credential_resolver=resolver,
        )
    assert exc.value.code == DemisAdapterErrorCode.UNSUPPORTED_DBMS
    assert resolver.resolve_calls == []


def test_fake_adapter_kinds_do_not_resolve_credentials() -> None:
    for kind in ("fake", "test", "mock", "memory"):
        resolver = _TrackingCredentialResolver(
            {"env:DEMIS_DB_PASSWORD": "test-secret-value"}
        )
        with pytest.raises(DemisAdapterError) as exc:
            create_readonly_demis_adapter(
                _eligible_snapshot(dbms_type=kind),
                credential_resolver=resolver,
            )
        assert exc.value.code == DemisAdapterErrorCode.UNSUPPORTED_DBMS
        assert resolver.resolve_calls == []


def test_unsupported_dbms_fail_closed() -> None:
    with pytest.raises(DemisAdapterError) as exc:
        create_readonly_demis_adapter(
            _eligible_snapshot(dbms_type="oracle"),
            credential_resolver=_resolver(),
        )
    assert exc.value.code == DemisAdapterErrorCode.UNSUPPORTED_DBMS
    assert exc.value.failure_category == DemisAdapterErrorCode.UNSUPPORTED_DBMS


def test_fake_adapter_not_selectable_via_production_factory() -> None:
    for kind in ("fake", "test", "mock", "memory"):
        with pytest.raises(DemisAdapterError) as exc:
            create_readonly_demis_adapter(
                _eligible_snapshot(dbms_type=kind),
                credential_resolver=_resolver(),
            )
        assert exc.value.code == DemisAdapterErrorCode.UNSUPPORTED_DBMS


class _TrackingCredentialResolver:
    """Test double that records resolve invocations without logging secrets."""

    def __init__(self, mapping: dict[str, str]) -> None:
        self._inner = FakeCredentialResolver(mapping)
        self.resolve_calls: list[str] = []

    def resolve(self, credential_secret_ref: str):
        self.resolve_calls.append(credential_secret_ref)
        return self._inner.resolve(credential_secret_ref)


def test_diagnostics_sanitized_no_live_connection() -> None:
    adapter = build_fake_readonly_demis_adapter(dbms_type="fake")
    diag = adapter.diagnostics()
    assert isinstance(diag, DemisAdapterDiagnostics)
    assert diag.configured is True
    assert diag.live_connection_tested is False
    assert diag.reachable is None
    assert diag.read_only is None
    dumped = diag.model_dump()
    for forbidden in ("host", "port", "username", "password", "dsn", "credential"):
        assert forbidden not in dumped


def test_result_repr_omits_rows_and_errors_omit_rows() -> None:
    sensitive = {"patient_id": "P-999", "name": "SECRET_PATIENT"}
    result = ReadonlyQueryResult(
        columns=["patient_id", "name"],
        rows=[sensitive],
        row_count=1,
        truncated=False,
        elapsed_ms=3,
    )
    assert "SECRET_PATIENT" not in repr(result)
    assert "P-999" not in repr(result)

    adapter = FakeReadOnlyDemisAdapter(
        rows=[sensitive],
        columns=["patient_id", "name"],
        simulate_execution_failure=True,
    )
    with pytest.raises(DemisAdapterError) as exc:
        adapter.execute_readonly(
            ReadonlyQueryRequest(
                sql_text="SELECT patient_id, name FROM patients",
                parameters={},
                timeout_seconds=5,
                row_limit=10,
            )
        )
    assert "SECRET_PATIENT" not in str(exc.value)
    assert "P-999" not in str(exc.value)
    assert "SECRET_PATIENT" not in repr(exc.value)


def test_credentials_host_user_dsn_never_in_factory_errors() -> None:
    sensitive_host = "secret-host.demis.internal"
    sensitive_user = "secret_ro_user"
    sensitive_db = "SECRET_SERVICE"
    secret = "super-secret-password-xyz"
    resolver = FakeCredentialResolver({"env:DEMIS_DB_PASSWORD": secret})
    snapshot = _eligible_snapshot(
        host=sensitive_host,
        username=sensitive_user,
        database_name=sensitive_db,
        dbms_type="postgresql",
    )
    with pytest.raises(DemisAdapterError) as exc:
        create_readonly_demis_adapter(snapshot, credential_resolver=resolver)
    text = str(exc.value) + repr(exc.value)
    assert sensitive_host not in text
    assert sensitive_user not in text
    assert sensitive_db not in text
    assert secret not in text
    assert "env:DEMIS_DB_PASSWORD" not in text


def test_credential_material_repr_redacts_secret() -> None:
    material = _resolver().resolve("env:DEMIS_DB_PASSWORD")
    assert "test-secret-value" not in repr(material)
    assert "test-secret-value" not in str(material)
    assert material.get_secret() == "test-secret-value"


def test_no_public_execution_route_registered() -> None:
    from app.main import create_app

    app = create_app(init_db_on_startup=False)
    paths = set(app.openapi()["paths"].keys())
    # Live execute / DEMIS adapter HTTP surfaces remain forbidden.
    # Preview (`/api/v1/query-executions/preview`) is a separate eligibility API.
    forbidden_exact = {
        "/api/v1/query-executions/execute",
        "/api/v1/demis",
        "/api/v1/readonly-query",
    }
    assert forbidden_exact.isdisjoint(paths)
    for path in paths:
        lowered = path.casefold()
        assert not lowered.endswith("/execute"), path
        assert "/demis/" not in lowered and not lowered.endswith("/demis"), path
    assert "/api/v1/audit-events" in paths
    assert "post" not in {
        method.casefold()
        for method in app.openapi()["paths"]["/api/v1/audit-events"].keys()
    }
    # Import kept for route module presence; foundation adds no demis routes.
    assert api_router is not None


def test_result_rows_not_emitted_via_logging_handler(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sensitive = {"patient_id": "P-HIDDEN", "note": "SENSITIVE_NOTE_VALUE"}
    adapter = build_fake_readonly_demis_adapter(
        columns=["patient_id", "note"],
        rows=[sensitive],
    )
    with caplog.at_level(logging.DEBUG):
        result = adapter.execute_readonly(
            ReadonlyQueryRequest(
                sql_text="SELECT patient_id, note FROM notes WHERE id = :id",
                parameters={"id": 1},
                timeout_seconds=5,
                row_limit=10,
            )
        )
        logging.getLogger("test.demis").info("result=%r", result)
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "SENSITIVE_NOTE_VALUE" not in joined
    assert "P-HIDDEN" not in joined


def test_protocol_surface_has_diagnostics_and_execute() -> None:
    adapter = build_fake_readonly_demis_adapter()
    assert callable(adapter.diagnostics)
    assert callable(adapter.execute_readonly)
    diag = adapter.diagnostics()
    assert diag.live_connection_tested is False
