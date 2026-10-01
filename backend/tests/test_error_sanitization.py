"""Public API error sanitization regressions.

Assert representative secret/sensitive fragments never appear in JSON error
bodies for auth, Catalog, Connection Profile, execution, and LLM failures.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.errors import AuthErrorCode
from app.schemas.query_template import QueryTemplateCreateRequest
from app.services.catalog_active import activate_catalog_revision
from app.services.catalog_package_import import import_catalog_package_bytes
from app.services.query_template import create_query_template
from tests.catalog_package_fixtures import (
    DEFAULT_SOURCE,
    build_core_documents,
    build_package_zip,
)

pytestmark = pytest.mark.integration

SOURCE = dict(DEFAULT_SOURCE)
SOURCE_NAME = SOURCE["source_name"]

FORBIDDEN_FRAGMENTS = (
    "DQA_DB_PASSWORD",
    "super-secret-db-password",
    "demis-live-password-value",
    "postgresql+psycopg://",
    "LLM_API_KEY",
    "sk-test-llm-secret-key",
    "Traceback (most recent call last)",
    "/workspace/backend/app/",
    "SELECT secret_patient_id FROM dual",
    "row_secret_phi_value",
)


def _headers(actor: str = "admin", roles: str = "administrator") -> dict[str, str]:
    return {
        "X-DQA-Dev-Actor": actor,
        "X-DQA-Dev-Roles": roles,
    }


def _assert_sanitized(payload: Any) -> None:
    text = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    lowered = text.lower()
    for fragment in FORBIDDEN_FRAGMENTS:
        assert fragment.lower() not in lowered, f"leaked fragment: {fragment!r} in {text!r}"


def _seed_catalog(session: Session, *, fingerprint: str) -> int:
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
    return revision.id


def test_auth_failure_errors_are_sanitized(unauth_client: TestClient) -> None:
    missing = unauth_client.get("/api/v1/catalog/active")
    assert missing.status_code == 401
    _assert_sanitized(missing.json())

    denied = unauth_client.post(
        "/api/v1/catalog/packages/validate",
        headers=_headers("ops", "query_operator"),
        files={"file": ("pkg.zip", b"not-a-zip", "application/zip")},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED
    _assert_sanitized(denied.json())


def test_disabled_provider_error_sanitized(
    monkeypatch: pytest.MonkeyPatch, test_settings_env: dict[str, str]
) -> None:
    monkeypatch.setenv("DQA_AUTH_PROVIDER", "disabled")
    monkeypatch.setenv("DQA_DB_PASSWORD", "super-secret-db-password")
    from app.adapters.db.session import get_engine, get_session_factory
    from app.core.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    application = create_app(init_db_on_startup=False)
    with TestClient(application) as client:
        response = client.get(
            "/api/v1/catalog/active",
            headers=_headers(),
        )
    assert response.status_code == 503
    _assert_sanitized(response.json())
    get_settings.cache_clear()


def test_catalog_invalid_package_error_sanitized(unauth_db_client: TestClient) -> None:
    response = unauth_db_client.post(
        "/api/v1/catalog/packages/validate",
        headers=_headers(),
        files={"file": ("pkg.zip", b"not-a-real-zip-archive", "application/zip")},
    )
    assert response.status_code in {400, 413}
    _assert_sanitized(response.json())


def test_connection_profile_error_sanitized(
    db_session: Session, unauth_db_client: TestClient
) -> None:
    response = unauth_db_client.get(
        "/api/v1/connection-profiles/999999",
        headers=_headers(),
    )
    assert response.status_code == 404
    body = response.json()
    _assert_sanitized(body)
    assert "demis-live-password-value" not in json.dumps(body)

    # Diagnostics must remain configuration-level and must not resolve secrets.
    created = unauth_db_client.post(
        "/api/v1/connection-profiles",
        headers=_headers(),
        json={
            "name": "probe",
            "source_name": SOURCE_NAME,
            "environment": "prod",
            "credential_secret_ref": "env:DEMIS_SECRET_ORACLE_PASSWORD",
            "host": "demis.example.internal",
            "username": "demis_ro",
        },
    )
    assert created.status_code == 201, created.text
    _assert_sanitized(created.json())
    diagnostics = unauth_db_client.get(
        f"/api/v1/connection-profiles/{created.json()['id']}/diagnostics",
        headers=_headers(),
    )
    assert diagnostics.status_code == 200
    diag_text = json.dumps(diagnostics.json())
    _assert_sanitized(diag_text)
    assert "demis-live-password-value" not in diag_text


def test_execution_unavailable_error_sanitized(
    db_session: Session, unauth_db_client: TestClient
) -> None:
    _seed_catalog(db_session, fingerprint="fp-sanitize-exec")
    template = create_query_template(
        db_session,
        QueryTemplateCreateRequest(
            stable_key="sanitize.exec",
            name="sanitize exec",
            description=None,
            source_name=SOURCE_NAME,
            target_schemas=["DEMIS_OWNER"],
            sql_text="SELECT 1 AS n FROM dual",
            parameter_schema=[],
            row_limit=10,
            timeout_seconds=15,
        ),
        actor="admin",
    )
    # Approve + enable via HTTP as administrator.
    db_session.commit()
    template_id = template.id
    version_id = template.version.id

    submit = unauth_db_client.post(
        f"/api/v1/query-templates/{template_id}/submit-review",
        headers=_headers(),
        json={},
    )
    assert submit.status_code == 200, submit.text
    approve = unauth_db_client.post(
        f"/api/v1/query-templates/{template_id}/approve",
        headers=_headers(),
        json={},
    )
    assert approve.status_code == 200, approve.text
    enable = unauth_db_client.post(
        f"/api/v1/query-templates/{template_id}/enable",
        headers=_headers(),
    )
    assert enable.status_code == 200, enable.text

    # Create incomplete/enabled profile so eligibility can reach adapter gap, or
    # preview without profile. Either path must stay sanitized.
    profile = unauth_db_client.post(
        "/api/v1/connection-profiles",
        headers=_headers(),
        json={
            "name": "sanitize-profile",
            "source_name": SOURCE_NAME,
            "environment": "prod",
            "dbms_type": "unknown_dbms",
            "host": "demis.example.internal",
            "port": 1521,
            "database_name": "FREEPDB1",
            "username": "demis_ro",
            "credential_secret_ref": "env:DEMIS_SECRET_ORACLE_PASSWORD",
        },
    )
    assert profile.status_code == 201, profile.text
    profile_id = profile.json()["id"]
    assert (
        unauth_db_client.post(
            f"/api/v1/connection-profiles/{profile_id}/enable",
            headers=_headers(),
        ).status_code
        == 200
    )

    preview = unauth_db_client.post(
        "/api/v1/query-executions/preview",
        headers=_headers("ops", "query_operator"),
        json={
            "source_name": SOURCE_NAME,
            "environment": "prod",
            "template_id": template_id,
            "version_id": version_id,
            "parameters": {},
        },
    )
    assert preview.status_code == 200, preview.text
    _assert_sanitized(preview.json())
    assert preview.json()["execution_available"] is False

    execute = unauth_db_client.post(
        "/api/v1/query-executions/execute",
        headers=_headers("ops", "query_operator"),
        json={
            "source_name": SOURCE_NAME,
            "environment": "prod",
            "template_id": template_id,
            "version_id": version_id,
            "parameters": {},
        },
    )
    assert execute.status_code in {409, 503, 422, 400}
    _assert_sanitized(execute.json())


def test_llm_provider_failure_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    unauth_db_client: TestClient,
) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("LLM_API_KEY", "sk-test-llm-secret-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    from app.core.config import get_settings

    get_settings.cache_clear()

    _seed_catalog(db_session, fingerprint="fp-sanitize-llm")
    template = create_query_template(
        db_session,
        QueryTemplateCreateRequest(
            stable_key="sanitize.llm",
            name="sanitize llm",
            description=None,
            source_name=SOURCE_NAME,
            target_schemas=["DEMIS_OWNER"],
            sql_text="SELECT 1 AS n FROM dual",
            parameter_schema=[],
            row_limit=10,
            timeout_seconds=15,
        ),
        actor="admin",
    )
    db_session.commit()
    template_id = template.id
    assert (
        unauth_db_client.post(
            f"/api/v1/query-templates/{template_id}/submit-review",
            headers=_headers(),
            json={},
        ).status_code
        == 200
    )
    assert (
        unauth_db_client.post(
            f"/api/v1/query-templates/{template_id}/approve",
            headers=_headers(),
            json={},
        ).status_code
        == 200
    )
    assert (
        unauth_db_client.post(
            f"/api/v1/query-templates/{template_id}/enable",
            headers=_headers(),
        ).status_code
        == 200
    )

    response = unauth_db_client.post(
        "/api/v1/query-recommendations",
        headers=_headers("ops", "query_operator"),
        json={
            "source_name": SOURCE_NAME,
            "request_text": "show me something SELECT secret_patient_id FROM dual",
        },
    )
    # May be 200 with empty ranking or sanitized provider error depending on path.
    assert response.status_code in {200, 502, 503, 504, 400}
    _assert_sanitized(response.json())
    get_settings.cache_clear()
