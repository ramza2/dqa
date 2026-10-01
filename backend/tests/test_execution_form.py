"""Query Execution form metadata API tests."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.adapters.demis.types import MAX_SQL_TEXT_LENGTH
from app.adapters.execution.errors import ExecutionPreviewErrorCode
from app.auth.errors import AuthErrorCode
from app.core.config import get_settings
from app.models.connection_profile import ConnectionProfile
from app.models.query_audit import QueryAuditEvent
from app.models.query_template import QueryTemplateVersion
from app.services.catalog_active import activate_catalog_revision
from app.services.catalog_package_import import import_catalog_package_bytes
from sqlalchemy import select
from tests.catalog_package_fixtures import (
    DEFAULT_SOURCE,
    build_core_documents,
    build_package_zip,
)

pytestmark = pytest.mark.integration

SOURCE = dict(DEFAULT_SOURCE)
FORM_PATH = "/api/v1/query-executions/form"
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
        "stable_key": "exec.form.wards",
        "name": "병동 조회",
        "description": "병동 파라미터 폼",
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
                "description": "병동 식별자",
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
        "environment": "dev",
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


def _setup_form(
    db_session: Session,
    db_client: TestClient,
    *,
    fingerprint: str = "fp-form",
    template_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    revision = _import_and_activate(db_session, fingerprint=fingerprint)
    db_session.commit()
    created = db_client.post(
        "/api/v1/query-templates",
        json=_template_body(**(template_overrides or {})),
    )
    assert created.status_code == 201, created.text
    detail = _approve_enable(db_client, created.json()["id"])
    return {
        "revision": revision,
        "template": detail,
        "template_id": detail["id"],
        "version_id": detail["version"]["id"],
        "sql_text": detail["version"]["sql_text"],
    }


def _form_params(fixture: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "source_name": SOURCE["source_name"],
        "template_id": fixture["template_id"],
        "version_id": fixture["version_id"],
    }
    params.update(overrides)
    return params


def test_form_happy_path_parameters_and_environments(
    db_session: Session, db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _setup_form(db_session, db_client, fingerprint="fp-form-happy")
    _ensure_profile(db_client, environment="dev")
    _ensure_profile(
        db_client,
        environment="qa",
        name="QA profile",
        host="demis.qa.example",
    )
    disabled = _ensure_profile(
        db_client,
        environment="staging",
        name="Staging disabled",
        enabled=False,
    )
    assert disabled["enabled"] is False

    resolve = MagicMock(side_effect=AssertionError("resolve must not be called"))
    factory = MagicMock(side_effect=AssertionError("adapter factory must not be called"))
    monkeypatch.setattr(
        "app.adapters.demis.env_credentials.EnvironmentCredentialResolver.resolve",
        resolve,
        raising=False,
    )
    monkeypatch.setattr(
        "app.adapters.demis.factory.create_readonly_demis_adapter",
        factory,
    )
    monkeypatch.setattr(
        "app.adapters.demis.credential_factory.create_credential_resolver",
        MagicMock(side_effect=AssertionError("credential resolver must not be created")),
    )

    response = db_client.get(FORM_PATH, params=_form_params(fixture))
    assert response.status_code == 200, response.text
    body = response.json()
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers.get("pragma") == "no-cache"

    assert body["source_name"] == SOURCE["source_name"]
    assert body["catalog_revision_id"] == fixture["revision"].id
    assert body["catalog_fingerprint"] == "fp-form-happy"
    assert body["template"] == {
        "template_id": fixture["template_id"],
        "version_id": fixture["version_id"],
        "version": fixture["template"]["version"]["version"],
        "stable_key": "exec.form.wards",
        "name": "병동 조회",
        "description": "병동 파라미터 폼",
    }

    params_by_name = {item["name"]: item for item in body["parameters"]}
    assert params_by_name["ward_cd"]["sensitive"] is True
    assert params_by_name["ward_cd"]["label"] == "병동 코드"
    assert params_by_name["ward_cd"]["pattern"] == r"^[A-Z][0-9]{2}$"
    assert "value" not in params_by_name["ward_cd"]
    assert params_by_name["from_date"]["default"] == "2024-01-01"
    assert params_by_name["from_date"]["required"] is False

    envs = {item["environment"]: item for item in body["environments"]}
    assert set(envs) == {"dev", "qa"}
    assert "staging" not in envs
    assert envs["dev"]["execution_available"] is True
    assert envs["dev"]["execution_blockers"] == []
    assert envs["qa"]["execution_available"] is True
    assert envs["qa"]["execution_blockers"] == []

    text = response.text
    assert "sql_text" not in body
    assert "SELECT ward_cd" not in text
    assert "demis.internal.example" not in text
    assert "demis.qa.example" not in text
    assert "dqa_ro" not in text
    assert ALLOWED_REF not in text
    assert "credential_secret_ref" not in text
    assert "connection_profile_id" not in text
    assert "host" not in text
    assert "username" not in text

    resolve.assert_not_called()
    factory.assert_not_called()

    audits = list(db_session.scalars(select(QueryAuditEvent)).all())
    assert audits == []


def test_incomplete_enabled_profile_returned_unavailable(
    db_session: Session, db_client: TestClient
) -> None:
    fixture = _setup_form(db_session, db_client, fingerprint="fp-form-incomplete")
    profile = _ensure_profile(db_client, environment="dev")
    row = db_session.get(ConnectionProfile, profile["id"])
    assert row is not None
    row.host = None
    db_session.commit()

    response = db_client.get(FORM_PATH, params=_form_params(fixture))
    assert response.status_code == 200
    envs = response.json()["environments"]
    assert len(envs) == 1
    assert envs[0]["environment"] == "dev"
    assert envs[0]["execution_available"] is False
    assert envs[0]["execution_blockers"] == ["CONNECTION_PROFILE_INCOMPLETE"]
    assert "demis.internal.example" not in response.text


def test_stale_and_unapproved_rejected(
    db_session: Session, db_client: TestClient
) -> None:
    fixture = _setup_form(db_session, db_client, fingerprint="fp-form-stale")
    stale_version_id = fixture["version_id"]
    newer = db_client.post(
        f"/api/v1/query-templates/{fixture['template_id']}/versions",
        json={},
    )
    assert newer.status_code == 201

    stale = db_client.get(
        FORM_PATH,
        params=_form_params(fixture, version_id=stale_version_id),
    )
    assert stale.status_code == 409
    assert (
        stale.json()["detail"]["code"]
        == ExecutionPreviewErrorCode.STALE_TEMPLATE_VERSION
    )

    draft = db_client.post(
        "/api/v1/query-templates",
        json=_template_body(stable_key="exec.form.draft"),
    )
    assert draft.status_code == 201
    draft_id = draft.json()["id"]
    draft_version = draft.json()["version"]["id"]
    not_enabled = db_client.get(
        FORM_PATH,
        params={
            "source_name": SOURCE["source_name"],
            "template_id": draft_id,
            "version_id": draft_version,
        },
    )
    assert not_enabled.status_code == 409
    assert (
        not_enabled.json()["detail"]["code"]
        == ExecutionPreviewErrorCode.TEMPLATE_NOT_ELIGIBLE
    )


def test_catalog_mismatch_and_sql_gates(
    db_session: Session, db_client: TestClient
) -> None:
    fixture = _setup_form(db_session, db_client, fingerprint="fp-form-catalog")
    # Activate a different package fingerprint for same source by importing new READY pkg.
    _import_and_activate(db_session, fingerprint="fp-form-catalog-other")
    db_session.commit()

    mismatch = db_client.get(FORM_PATH, params=_form_params(fixture))
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"]["code"] == ExecutionPreviewErrorCode.CATALOG_MISMATCH

    fixture2 = _setup_form(
        db_session,
        db_client,
        fingerprint="fp-form-sql-len",
        template_overrides={"stable_key": "exec.form.sql.len"},
    )
    version = db_session.get(QueryTemplateVersion, fixture2["version_id"])
    assert version is not None
    version.sql_text = "SELECT 1 FROM dual -- " + ("x" * (MAX_SQL_TEXT_LENGTH + 1))
    db_session.commit()

    too_long = db_client.get(FORM_PATH, params=_form_params(fixture2))
    assert too_long.status_code == 409
    assert (
        too_long.json()["detail"]["code"]
        == ExecutionPreviewErrorCode.TEMPLATE_NOT_ELIGIBLE
    )
    assert "SELECT 1 FROM dual" not in too_long.text
    assert "xxxxx" not in too_long.text


def test_sql_unsafe_rejected(db_session: Session, db_client: TestClient) -> None:
    fixture = _setup_form(
        db_session,
        db_client,
        fingerprint="fp-form-unsafe",
        template_overrides={"stable_key": "exec.form.unsafe"},
    )
    version = db_session.get(QueryTemplateVersion, fixture["version_id"])
    assert version is not None
    version.sql_text = "DELETE FROM dual WHERE ward_cd = :ward_cd"
    db_session.commit()

    response = db_client.get(FORM_PATH, params=_form_params(fixture))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == ExecutionPreviewErrorCode.SQL_UNSAFE
    assert "DELETE FROM dual" not in response.text


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("query_operator", 200),
        ("administrator", 200),
        ("viewer", 403),
        ("auditor", 403),
        ("template_author", 403),
    ],
)
def test_form_rbac(
    db_session: Session,
    db_client: TestClient,
    unauth_db_client: TestClient,
    role: str,
    expected: int,
) -> None:
    fixture = _setup_form(
        db_session,
        db_client,
        fingerprint=f"fp-form-rbac-{role}",
        template_overrides={"stable_key": f"exec.form.rbac.{role}"},
    )
    _ensure_profile(db_client, environment="dev")
    response = unauth_db_client.get(
        FORM_PATH,
        params=_form_params(fixture),
        headers=_headers(f"user-{role}", role),
    )
    assert response.status_code == expected
    if expected == 403:
        assert response.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED


def test_missing_identity_401(unauth_db_client: TestClient) -> None:
    response = unauth_db_client.get(
        FORM_PATH,
        params={
            "source_name": "x",
            "template_id": 1,
            "version_id": 1,
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
        response = client.get(
            FORM_PATH,
            params={
                "source_name": "x",
                "template_id": 1,
                "version_id": 1,
            },
            headers=_headers("op", "query_operator"),
        )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == AuthErrorCode.PROVIDER_NOT_CONFIGURED
    get_settings.cache_clear()


def test_form_does_not_log_secrets_or_sql(
    db_session: Session,
    db_client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fixture = _setup_form(db_session, db_client, fingerprint="fp-form-nolog")
    _ensure_profile(db_client, environment="dev")
    with caplog.at_level(logging.DEBUG):
        response = db_client.get(FORM_PATH, params=_form_params(fixture))
        logging.getLogger("test.form").info("status=%s", response.status_code)
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert response.status_code == 200
    assert "demis.internal.example" not in joined
    assert ALLOWED_REF not in joined
    assert "SELECT ward_cd" not in joined
