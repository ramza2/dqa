"""Execution preview + eligibility gate tests (no DEMIS connection)."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.adapters.execution.errors import ExecutionPreviewErrorCode
from app.auth.errors import AuthErrorCode
from app.core.config import get_settings
from app.models.catalog_active import CatalogActiveRevision
from app.models.connection_profile import ConnectionProfile
from app.schemas.execution_preview import ExecutionPreviewRequest
from app.services.catalog_active import activate_catalog_revision
from app.services.catalog_package_import import import_catalog_package_bytes
from app.services.execution_eligibility import evaluate_execution_eligibility
from tests.catalog_package_fixtures import (
    DEFAULT_SOURCE,
    build_core_documents,
    build_package_zip,
)

pytestmark = pytest.mark.integration

SOURCE = dict(DEFAULT_SOURCE)
ENVIRONMENT = "dev"
PREVIEW_PATH = "/api/v1/query-executions/preview"


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
        "stable_key": "exec.preview.wards",
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
        "credential_secret_ref": "env:DEMIS_SECRET_PASSWORD",
    }
    body.update(overrides)
    # Drop keys explicitly set to None so optional fields stay unset.
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
    fingerprint: str = "fp-exec-preview",
    template_overrides: dict[str, Any] | None = None,
    profile_overrides: dict[str, Any] | None = None,
    enable_template: bool = True,
) -> dict[str, Any]:
    revision = _import_and_activate(db_session, fingerprint=fingerprint)
    db_session.commit()
    created = db_client.post(
        "/api/v1/query-templates",
        json=_template_body(**(template_overrides or {})),
    )
    assert created.status_code == 201, created.text
    detail = created.json()
    if enable_template:
        detail = _approve_enable(db_client, detail["id"])
    profile = _ensure_profile(db_client, **(profile_overrides or {}))
    return {
        "revision": revision,
        "template": detail,
        "profile": profile,
        "version_id": detail["version"]["id"],
        "template_id": detail["id"],
    }


def _preview_body(fixture: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "source_name": SOURCE["source_name"],
        "environment": ENVIRONMENT,
        "template_id": fixture["template_id"],
        "version_id": fixture["version_id"],
        "parameters": {"ward_cd": "A01"},
    }
    body.update(overrides)
    return body


def test_happy_preview_no_demis_call(
    db_session: Session, db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _setup_eligible(db_session, db_client)
    monkeypatch.setattr(
        "app.adapters.demis.factory.create_readonly_demis_adapter",
        MagicMock(side_effect=AssertionError("factory must not be called")),
    )

    response = db_client.post(PREVIEW_PATH, json=_preview_body(fixture))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source_name"] == SOURCE["source_name"]
    assert body["environment"] == ENVIRONMENT
    assert body["catalog_revision_id"] == fixture["revision"].id
    assert body["catalog_fingerprint"] == "fp-exec-preview"
    assert body["template_id"] == fixture["template_id"]
    assert body["version_id"] == fixture["version_id"]
    assert body["version"] == 1
    assert body["connection_profile_id"] == fixture["profile"]["id"]
    assert body["resolved_parameters"] == {
        "ward_cd": "A01",
        "from_date": "2024-01-01",
    }
    assert body["sensitive_parameter_names"] == ["ward_cd"]
    assert body["row_limit"] == 50
    assert body["timeout_seconds"] == 15
    assert body["execution_available"] is False
    assert body["execution_blockers"] == ["DEMIS_ADAPTER_UNAVAILABLE"]
    assert "sql_text" not in body
    assert "host" not in body
    assert "username" not in body
    assert "credential_secret_ref" not in body
    assert "demis.internal.example" not in response.text
    assert "dqa_ro" not in response.text
    assert "env:DEMIS_SECRET_PASSWORD" not in response.text
    assert response.headers["cache-control"] == "no-store, private"


def test_approved_enabled_required(db_session: Session, db_client: TestClient) -> None:
    fixture = _setup_eligible(db_session, db_client, enable_template=False)
    response = db_client.post(PREVIEW_PATH, json=_preview_body(fixture))
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == ExecutionPreviewErrorCode.TEMPLATE_NOT_ELIGIBLE


def test_stale_version_rejected(db_session: Session, db_client: TestClient) -> None:
    fixture = _setup_eligible(db_session, db_client)
    stale_version_id = fixture["version_id"]
    newer = db_client.post(
        f"/api/v1/query-templates/{fixture['template_id']}/versions",
        json={},
    )
    assert newer.status_code == 201, newer.text
    assert newer.json()["version"]["id"] != stale_version_id

    response = db_client.post(
        PREVIEW_PATH,
        json=_preview_body(fixture, version_id=stale_version_id),
    )
    assert response.status_code == 409
    assert (
        response.json()["detail"]["code"]
        == ExecutionPreviewErrorCode.STALE_TEMPLATE_VERSION
    )


def test_source_mismatch(db_session: Session, db_client: TestClient) -> None:
    fixture = _setup_eligible(db_session, db_client)
    response = db_client.post(
        PREVIEW_PATH,
        json=_preview_body(fixture, source_name="other_source"),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == ExecutionPreviewErrorCode.TEMPLATE_NOT_ELIGIBLE


def test_active_catalog_missing(db_session: Session, db_client: TestClient) -> None:
    fixture = _setup_eligible(db_session, db_client, fingerprint="fp-missing-active")
    db_session.execute(delete(CatalogActiveRevision))
    db_session.commit()

    response = db_client.post(PREVIEW_PATH, json=_preview_body(fixture))
    assert response.status_code == 404
    assert (
        response.json()["detail"]["code"]
        == ExecutionPreviewErrorCode.ACTIVE_CATALOG_NOT_FOUND
    )


def test_catalog_fingerprint_mismatch(
    db_session: Session, db_client: TestClient
) -> None:
    fixture = _setup_eligible(db_session, db_client, fingerprint="fp-old")
    from app.models.query_template import QueryTemplateVersion

    version = db_session.get(QueryTemplateVersion, fixture["version_id"])
    assert version is not None
    version.catalog_fingerprint_constraint = "fp-stale-other"
    db_session.commit()

    response = db_client.post(PREVIEW_PATH, json=_preview_body(fixture))
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == ExecutionPreviewErrorCode.CATALOG_MISMATCH


def test_unsafe_sql_rejected(db_session: Session, db_client: TestClient) -> None:
    fixture = _setup_eligible(
        db_session,
        db_client,
        fingerprint="fp-unsafe-sql",
        template_overrides={
            "stable_key": "exec.preview.unsafe",
            "sql_text": "DELETE FROM T WHERE ward_cd = :ward_cd",
            "parameter_schema": [
                {
                    "name": "ward_cd",
                    "label": "병동",
                    "type": "string",
                    "required": True,
                }
            ],
        },
    )
    response = db_client.post(
        PREVIEW_PATH,
        json=_preview_body(fixture, parameters={"ward_cd": "A01"}),
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == ExecutionPreviewErrorCode.SQL_UNSAFE
    assert "DELETE FROM" not in response.text


def test_undeclared_parameter_rejected(
    db_session: Session, db_client: TestClient
) -> None:
    fixture = _setup_eligible(db_session, db_client)
    response = db_client.post(
        PREVIEW_PATH,
        json=_preview_body(
            fixture,
            parameters={"ward_cd": "A01", "extra_secret": "SHOULD_NOT_APPEAR"},
        ),
    )
    assert response.status_code == 422
    assert (
        response.json()["detail"]["code"]
        == ExecutionPreviewErrorCode.PARAMETER_UNDECLARED
    )
    assert "SHOULD_NOT_APPEAR" not in response.text


def test_missing_required_and_default_parameters(
    db_session: Session, db_client: TestClient
) -> None:
    fixture = _setup_eligible(db_session, db_client)
    missing = db_client.post(
        PREVIEW_PATH,
        json=_preview_body(fixture, parameters={}),
    )
    assert missing.status_code == 422
    assert missing.json()["detail"]["code"] == ExecutionPreviewErrorCode.PARAMETER_INVALID

    ok = db_client.post(
        PREVIEW_PATH,
        json=_preview_body(fixture, parameters={"ward_cd": "B02"}),
    )
    assert ok.status_code == 200
    assert ok.json()["resolved_parameters"]["from_date"] == "2024-01-01"
    assert ok.json()["resolved_parameters"]["ward_cd"] == "B02"
    assert ok.json()["sensitive_parameter_names"] == ["ward_cd"]


def test_invalid_parameter_type(db_session: Session, db_client: TestClient) -> None:
    fixture = _setup_eligible(db_session, db_client)
    response = db_client.post(
        PREVIEW_PATH,
        json=_preview_body(fixture, parameters={"ward_cd": 123}),
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == ExecutionPreviewErrorCode.PARAMETER_INVALID


def test_connection_profile_missing(db_session: Session, db_client: TestClient) -> None:
    _import_and_activate(db_session, fingerprint="fp-cp-missing")
    db_session.commit()
    created = db_client.post("/api/v1/query-templates", json=_template_body())
    assert created.status_code == 201
    detail = _approve_enable(db_client, created.json()["id"])
    missing = db_client.post(
        PREVIEW_PATH,
        json={
            "source_name": SOURCE["source_name"],
            "environment": ENVIRONMENT,
            "template_id": detail["id"],
            "version_id": detail["version"]["id"],
            "parameters": {"ward_cd": "A01"},
        },
    )
    assert missing.status_code == 404
    assert (
        missing.json()["detail"]["code"]
        == ExecutionPreviewErrorCode.CONNECTION_PROFILE_NOT_FOUND
    )


def test_connection_profile_disabled(db_session: Session, db_client: TestClient) -> None:
    fixture = _setup_eligible(
        db_session,
        db_client,
        fingerprint="fp-cp-disabled",
        template_overrides={"stable_key": "exec.preview.disabled_cp"},
        profile_overrides={"enabled": False, "environment": "qa"},
    )
    disabled = db_client.post(
        PREVIEW_PATH,
        json=_preview_body(fixture, environment="qa"),
    )
    assert disabled.status_code == 409
    assert (
        disabled.json()["detail"]["code"]
        == ExecutionPreviewErrorCode.CONNECTION_PROFILE_DISABLED
    )


def test_connection_profile_incomplete(
    db_session: Session, db_client: TestClient
) -> None:
    fixture = _setup_eligible(
        db_session,
        db_client,
        fingerprint="fp-cp-incomplete",
        template_overrides={"stable_key": "exec.preview.incomplete_cp"},
        profile_overrides={
            "environment": "stage",
            "name": "Incomplete profile",
        },
    )
    profile = db_session.get(ConnectionProfile, fixture["profile"]["id"])
    assert profile is not None
    profile.host = None
    profile.credential_secret_ref = None
    db_session.commit()

    incomplete = db_client.post(
        PREVIEW_PATH,
        json=_preview_body(fixture, environment="stage"),
    )
    assert incomplete.status_code == 409
    assert (
        incomplete.json()["detail"]["code"]
        == ExecutionPreviewErrorCode.CONNECTION_PROFILE_INCOMPLETE
    )
    assert "demis.internal.example" not in incomplete.text
    assert "env:DEMIS_SECRET_PASSWORD" not in incomplete.text


def test_caller_cannot_inject_sql_catalog_profile_limits() -> None:
    with pytest.raises(ValidationError):
        ExecutionPreviewRequest.model_validate(
            {
                "source_name": "s",
                "environment": "dev",
                "template_id": 1,
                "version_id": 1,
                "parameters": {},
                "sql_text": "SELECT 1",
            }
        )
    with pytest.raises(ValidationError):
        ExecutionPreviewRequest.model_validate(
            {
                "source_name": "s",
                "environment": "dev",
                "template_id": 1,
                "version_id": 1,
                "parameters": {},
                "connection_profile_id": 9,
            }
        )
    with pytest.raises(ValidationError):
        ExecutionPreviewRequest.model_validate(
            {
                "source_name": "s",
                "environment": "dev",
                "template_id": 1,
                "version_id": 1,
                "parameters": {},
                "catalog_revision_id": 3,
                "row_limit": 9999,
            }
        )


def test_limits_from_approved_template_only(
    db_session: Session, db_client: TestClient
) -> None:
    fixture = _setup_eligible(
        db_session,
        db_client,
        fingerprint="fp-limits",
        template_overrides={"row_limit": 7, "timeout_seconds": 9},
    )
    response = db_client.post(
        PREVIEW_PATH,
        json=_preview_body(
            fixture,
            parameters={"ward_cd": "A01", "row_limit": 1},
        ),
    )
    assert response.status_code == 422
    assert (
        response.json()["detail"]["code"]
        == ExecutionPreviewErrorCode.PARAMETER_UNDECLARED
    )

    ok = db_client.post(PREVIEW_PATH, json=_preview_body(fixture))
    assert ok.status_code == 200
    assert ok.json()["row_limit"] == 7
    assert ok.json()["timeout_seconds"] == 9


def test_no_credential_resolver_or_adapter_execute(
    db_session: Session, db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _setup_eligible(db_session, db_client, fingerprint="fp-no-secret")
    monkeypatch.setattr(
        "app.adapters.demis.factory.create_readonly_demis_adapter",
        MagicMock(side_effect=AssertionError("factory must not be called")),
    )
    result = evaluate_execution_eligibility(
        db_session,
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
        template_id=fixture["template_id"],
        version_id=fixture["version_id"],
        parameters={"ward_cd": "A01"},
    )
    assert result.execution_available is False
    assert result.execution_blockers == ["DEMIS_ADAPTER_UNAVAILABLE"]


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("query_operator", 200),
        ("administrator", 200),
        ("viewer", 403),
        ("template_author", 403),
        ("auditor", 403),
        ("template_approver", 403),
    ],
)
def test_query_operate_rbac(
    db_session: Session,
    db_client: TestClient,
    unauth_db_client: TestClient,
    role: str,
    expected: int,
) -> None:
    fixture = _setup_eligible(
        db_session,
        db_client,
        fingerprint=f"fp-rbac-{role}",
        template_overrides={"stable_key": f"exec.rbac.{role}"},
    )

    response = unauth_db_client.post(
        PREVIEW_PATH,
        json=_preview_body(fixture),
        headers=_headers(f"user-{role}", role),
    )
    assert response.status_code == expected
    if expected == 403:
        assert response.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED


def test_missing_identity_401(unauth_db_client: TestClient) -> None:
    response = unauth_db_client.post(
        PREVIEW_PATH,
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
            PREVIEW_PATH,
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


def test_errors_and_logs_do_not_leak_secrets(
    db_session: Session,
    db_client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fixture = _setup_eligible(db_session, db_client, fingerprint="fp-leak")
    with caplog.at_level(logging.DEBUG):
        response = db_client.post(
            PREVIEW_PATH,
            json=_preview_body(
                fixture,
                parameters={"ward_cd": "A01", "from_date": "2024-02-02"},
            ),
        )
        logging.getLogger("test.execution_preview").info(
            "preview ok status=%s", response.status_code
        )
    assert response.status_code == 200
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "demis.internal.example" not in joined
    assert "env:DEMIS_SECRET_PASSWORD" not in joined
    assert "SELECT ward_cd" not in joined


def test_no_execute_route_yet(db_client: TestClient) -> None:
    from app.main import create_app

    app = create_app(init_db_on_startup=False)
    paths = set(app.openapi()["paths"].keys())
    assert PREVIEW_PATH in paths
    assert "/api/v1/query-executions/execute" not in paths
    assert db_client.post("/api/v1/query-executions/execute", json={}).status_code == 404
