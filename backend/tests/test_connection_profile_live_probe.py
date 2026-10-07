"""Explicit Connection Profile live DEMIS probe (Phase 25-A)."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.adapters.demis.errors import DemisAdapterError, DemisAdapterErrorCode, DemisProbeState
from app.adapters.demis.fake import FakeCredentialResolver
from app.adapters.demis.types import DemisAdapterDiagnostics
from app.auth.errors import AuthErrorCode

pytestmark = pytest.mark.integration


def _headers(actor: str, roles: str) -> dict[str, str]:
    return {
        "X-DQA-Dev-Actor": actor,
        "X-DQA-Dev-Roles": roles,
    }


def _create_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "Mock DEMIS profile",
        "source_name": "oracle_demis_mock",
        "environment": "dev-live-probe",
        "dbms_type": "oracle",
        "host": "demis.internal.example",
        "port": 1521,
        "database_name": "DEMIS",
        "username": "dqa_ro",
        "credential_secret_ref": "env:DEMIS_SECRET_PASSWORD",
    }
    body.update(overrides)
    return body


class _TrackingCredentialResolver:
    def __init__(self, mapping: dict[str, str] | None = None) -> None:
        self._inner = FakeCredentialResolver(mapping or {"env:DEMIS_SECRET_PASSWORD": "secret"})
        self.resolve_calls: list[str] = []

    def resolve(self, credential_secret_ref: str):
        self.resolve_calls.append(credential_secret_ref)
        return self._inner.resolve(credential_secret_ref)


class _ProbeAdapter:
    def __init__(self, *, probe_result: DemisAdapterDiagnostics | None = None, probe_error: DemisAdapterError | None = None) -> None:
        self._probe_result = probe_result
        self._probe_error = probe_error

    def probe_readonly(self) -> DemisAdapterDiagnostics:
        if self._probe_error is not None:
            raise self._probe_error
        assert self._probe_result is not None
        return self._probe_result


def _create_enabled_profile(db_client: TestClient, **overrides: Any) -> int:
    created = db_client.post("/api/v1/connection-profiles", json=_create_body(**overrides))
    assert created.status_code == 201, created.text
    profile_id = created.json()["id"]
    enabled = db_client.post(f"/api/v1/connection-profiles/{profile_id}/enable")
    assert enabled.status_code == 200
    return profile_id


def test_get_diagnostics_never_resolves_credentials_or_connects(
    db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracking = _TrackingCredentialResolver()

    def _forbidden_resolver() -> _TrackingCredentialResolver:
        raise AssertionError("credential resolver must not run for GET diagnostics")

    def _forbidden_factory(*_args, **_kwargs):
        raise AssertionError("adapter factory must not run for GET diagnostics")

    monkeypatch.setattr(
        "app.services.connection_profile.create_credential_resolver",
        _forbidden_resolver,
    )
    monkeypatch.setattr(
        "app.services.connection_profile.create_readonly_demis_adapter",
        _forbidden_factory,
    )

    profile_id = _create_enabled_profile(db_client, environment="diag-only")
    diagnostics = db_client.get(f"/api/v1/connection-profiles/{profile_id}/diagnostics")
    assert diagnostics.status_code == 200
    assert diagnostics.json()["live_connection_tested"] is False
    assert tracking.resolve_calls == []


def test_admin_test_connection_success(
    db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracking = _TrackingCredentialResolver()

    def _resolver() -> _TrackingCredentialResolver:
        return tracking

    def _factory(_profile, *, credential_resolver):
        credential_resolver.resolve("env:DEMIS_SECRET_PASSWORD")
        return _ProbeAdapter(
            probe_result=DemisAdapterDiagnostics(
                configured=True,
                dbms_type="oracle",
                live_connection_tested=True,
                reachable=True,
                read_only=True,
                failure_category=None,
            )
        )

    monkeypatch.setattr("app.services.connection_profile.create_credential_resolver", _resolver)
    monkeypatch.setattr("app.services.connection_profile.create_readonly_demis_adapter", _factory)

    profile_id = _create_enabled_profile(db_client, environment="probe-ok")
    response = db_client.post(f"/api/v1/connection-profiles/{profile_id}/test-connection")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUCCEEDED"
    assert body["live_connection_tested"] is True
    assert body["reachable"] is True
    assert body["read_only"] is True
    assert body["failure_category"] is None
    assert body["source_name"] == "oracle_demis_mock"
    assert tracking.resolve_calls == ["env:DEMIS_SECRET_PASSWORD"]
    assert "host" not in body
    assert "demis.internal.example" not in response.text


@pytest.mark.parametrize(
    "role",
    ["viewer", "template_author", "template_approver", "query_operator", "auditor"],
)
def test_non_admin_test_connection_forbidden(
    db_client: TestClient, unauth_db_client: TestClient, role: str
) -> None:
    profile_id = _create_enabled_profile(
        db_client, environment=f"probe-rbac-{role}"
    )
    response = unauth_db_client.post(
        f"/api/v1/connection-profiles/{profile_id}/test-connection",
        headers=_headers(f"user-{role}", role),
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED


def test_disabled_profile_fails_without_credential_resolve(
    db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracking = _TrackingCredentialResolver()
    monkeypatch.setattr(
        "app.services.connection_profile.create_credential_resolver",
        lambda: tracking,
    )

    created = db_client.post(
        "/api/v1/connection-profiles",
        json=_create_body(environment="probe-disabled"),
    )
    profile_id = created.json()["id"]

    response = db_client.post(f"/api/v1/connection-profiles/{profile_id}/test-connection")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["failure_category"] == DemisAdapterErrorCode.PROFILE_DISABLED
    assert body["live_connection_tested"] is False
    assert body["reachable"] is None
    assert body["read_only"] is None
    assert tracking.resolve_calls == []


def test_unsupported_dbms_fails_without_credential_resolve(
    db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracking = _TrackingCredentialResolver()
    monkeypatch.setattr(
        "app.services.connection_profile.create_credential_resolver",
        lambda: tracking,
    )

    profile_id = _create_enabled_profile(
        db_client,
        environment="probe-unsupported",
        dbms_type="postgresql",
    )
    response = db_client.post(f"/api/v1/connection-profiles/{profile_id}/test-connection")
    assert response.status_code == 200
    body = response.json()
    assert body["failure_category"] == DemisAdapterErrorCode.UNSUPPORTED_DBMS
    assert body["live_connection_tested"] is False
    assert tracking.resolve_calls == []


def test_credential_unavailable_sanitized(
    db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.connection_profile.create_credential_resolver",
        lambda: FakeCredentialResolver({}),
    )

    profile_id = _create_enabled_profile(db_client, environment="probe-no-cred")
    response = db_client.post(f"/api/v1/connection-profiles/{profile_id}/test-connection")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["failure_category"] == DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE
    assert body["live_connection_tested"] is False
    assert "env:DEMIS_SECRET_PASSWORD" not in response.text
    assert "secret" not in response.text.casefold()


def test_oracle_connect_failure_sanitized_via_service(
    db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _factory(_profile, *, credential_resolver):
        credential_resolver.resolve("env:DEMIS_SECRET_PASSWORD")
        raise DemisAdapterError(
            DemisAdapterErrorCode.CONNECTION_FAILED,
            "DEMIS read-only connection could not be established",
            probe=DemisProbeState(True, False, None),
        )

    monkeypatch.setattr(
        "app.services.connection_profile.create_credential_resolver",
        lambda: FakeCredentialResolver({"env:DEMIS_SECRET_PASSWORD": "pw"}),
    )
    monkeypatch.setattr("app.services.connection_profile.create_readonly_demis_adapter", _factory)

    profile_id = _create_enabled_profile(db_client, environment="probe-connect-fail")
    response = db_client.post(f"/api/v1/connection-profiles/{profile_id}/test-connection")
    assert response.status_code == 200
    body = response.json()
    assert body["failure_category"] == DemisAdapterErrorCode.CONNECTION_FAILED
    assert body["live_connection_tested"] is True
    assert body["reachable"] is False
    assert body["read_only"] is None
    assert "demis.internal.example" not in response.text


def test_timeout_sanitized(
    db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _factory(_profile, *, credential_resolver):
        credential_resolver.resolve("env:DEMIS_SECRET_PASSWORD")
        return _ProbeAdapter(
            probe_error=DemisAdapterError(
                DemisAdapterErrorCode.TIMEOUT,
                "DEMIS read-only query execution timed out",
                probe=DemisProbeState(True, False, None),
            )
        )

    monkeypatch.setattr(
        "app.services.connection_profile.create_credential_resolver",
        lambda: FakeCredentialResolver({"env:DEMIS_SECRET_PASSWORD": "pw"}),
    )
    monkeypatch.setattr("app.services.connection_profile.create_readonly_demis_adapter", _factory)

    profile_id = _create_enabled_profile(db_client, environment="probe-timeout")
    response = db_client.post(f"/api/v1/connection-profiles/{profile_id}/test-connection")
    body = response.json()
    assert body["failure_category"] == DemisAdapterErrorCode.TIMEOUT
    assert body["live_connection_tested"] is True
    assert body["reachable"] is False


def test_read_only_setup_failure_reachable_true(
    db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _factory(_profile, *, credential_resolver):
        credential_resolver.resolve("env:DEMIS_SECRET_PASSWORD")
        return _ProbeAdapter(
            probe_error=DemisAdapterError(
                DemisAdapterErrorCode.EXECUTION_FAILED,
                "DEMIS read-only query execution failed",
                probe=DemisProbeState(True, True, False),
            )
        )

    monkeypatch.setattr(
        "app.services.connection_profile.create_credential_resolver",
        lambda: FakeCredentialResolver({"env:DEMIS_SECRET_PASSWORD": "pw"}),
    )
    monkeypatch.setattr("app.services.connection_profile.create_readonly_demis_adapter", _factory)

    profile_id = _create_enabled_profile(db_client, environment="probe-readonly-fail")
    response = db_client.post(f"/api/v1/connection-profiles/{profile_id}/test-connection")
    body = response.json()
    assert body["live_connection_tested"] is True
    assert body["reachable"] is True
    assert body["read_only"] is False


def test_secrets_not_in_response_or_logs(
    db_client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "super-secret-password-marker"
    host = "secret-host.demis.internal"

    def _factory(_profile, *, credential_resolver):
        credential_resolver.resolve("env:DEMIS_SECRET_PASSWORD")
        raise DemisAdapterError(
            DemisAdapterErrorCode.CONNECTION_FAILED,
            "DEMIS read-only connection could not be established",
            probe=DemisProbeState(True, False, None),
        )

    monkeypatch.setattr(
        "app.services.connection_profile.create_credential_resolver",
        lambda: FakeCredentialResolver({"env:DEMIS_SECRET_PASSWORD": secret}),
    )
    monkeypatch.setattr("app.services.connection_profile.create_readonly_demis_adapter", _factory)

    profile_id = _create_enabled_profile(
        db_client,
        environment="probe-secret-scan",
        host=host,
        username="secret_user",
    )

    with caplog.at_level(logging.DEBUG):
        response = db_client.post(f"/api/v1/connection-profiles/{profile_id}/test-connection")

    text = response.text + "\n".join(record.getMessage() for record in caplog.records)
    for forbidden in (secret, host, "secret_user", "env:DEMIS_SECRET_PASSWORD", "postgresql://"):
        assert forbidden not in text
