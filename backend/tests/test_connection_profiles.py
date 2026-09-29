"""Connection Profile management and RBAC tests."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.errors import AuthErrorCode
from app.auth.models import Permission, Role
from app.auth.rbac import permissions_for_roles
from app.models.connection_profile import ConnectionProfile

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
        "environment": "dev",
        "dbms_type": "unspecified",
        "host": "demis.internal.example",
        "port": 1521,
        "database_name": "DEMIS",
        "username": "dqa_ro",
        "credential_secret_ref": "env:DEMIS_SECRET_PASSWORD",
    }
    body.update(overrides)
    return body


def test_administrator_crud_enable_disable_diagnostics(
    db_session: Session, db_client: TestClient
) -> None:
    created = db_client.post("/api/v1/connection-profiles", json=_create_body())
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["enabled"] is False
    assert body["created_by"] == "test-admin"
    assert body["credential_secret_ref"] == "env:DEMIS_SECRET_PASSWORD"
    assert "change-me" not in created.text
    assert "super-secret" not in created.text
    profile_id = body["id"]

    listed = db_client.get("/api/v1/connection-profiles")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    got = db_client.get(f"/api/v1/connection-profiles/{profile_id}")
    assert got.status_code == 200
    assert got.json()["source_name"] == "oracle_demis_mock"

    patched = db_client.patch(
        f"/api/v1/connection-profiles/{profile_id}",
        json={"name": "Updated profile", "port": 1522},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Updated profile"
    assert patched.json()["port"] == 1522
    assert patched.json()["updated_by"] == "test-admin"

    enabled = db_client.post(f"/api/v1/connection-profiles/{profile_id}/enable")
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True

    diagnostics = db_client.get(f"/api/v1/connection-profiles/{profile_id}/diagnostics")
    assert diagnostics.status_code == 200
    diag = diagnostics.json()
    assert diag["status"] == "CONFIGURED_ENABLED"
    assert diag["live_connection_tested"] is False
    assert diag["credential_reference_configured"] is True
    assert diag["target_metadata_configured"] is True
    assert "host" not in diag
    assert "demis.internal.example" not in diagnostics.text
    assert "change-me" not in diagnostics.text
    assert "password=" not in diagnostics.text.casefold()

    disabled = db_client.post(f"/api/v1/connection-profiles/{profile_id}/disable")
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False

    # Persistence never stored a secret value.
    stored = db_session.scalars(
        select(ConnectionProfile).where(ConnectionProfile.id == profile_id)
    ).one()
    assert stored.credential_secret_ref == "env:DEMIS_SECRET_PASSWORD"
    assert stored.credential_secret_ref is not None
    assert "secret-value" not in (stored.credential_secret_ref or "")


def test_duplicate_source_environment_conflict(
    db_session: Session, db_client: TestClient
) -> None:
    assert (
        db_client.post("/api/v1/connection-profiles", json=_create_body()).status_code
        == 201
    )
    dup = db_client.post("/api/v1/connection-profiles", json=_create_body())
    assert dup.status_code == 409
    assert (
        dup.json()["detail"]["code"]
        == "CONNECTION_PROFILE_DUPLICATE_SOURCE_ENVIRONMENT"
    )


def test_rejects_inline_secret_looking_credential_ref(db_client: TestClient) -> None:
    response = db_client.post(
        "/api/v1/connection-profiles",
        json=_create_body(credential_secret_ref="password=super-secret"),
    )
    assert response.status_code == 422
    assert "super-secret" not in response.text


def test_incomplete_diagnostics(db_session: Session, db_client: TestClient) -> None:
    created = db_client.post(
        "/api/v1/connection-profiles",
        json=_create_body(
            host=None,
            port=None,
            credential_secret_ref=None,
            name="Incomplete",
            environment="staging",
        ),
    )
    assert created.status_code == 201
    profile_id = created.json()["id"]
    diagnostics = db_client.get(f"/api/v1/connection-profiles/{profile_id}/diagnostics")
    assert diagnostics.status_code == 200
    body = diagnostics.json()
    assert body["status"] == "INCOMPLETE"
    assert body["live_connection_tested"] is False
    codes = {issue["code"] for issue in body["issues"]}
    assert "CREDENTIAL_REFERENCE_MISSING" in codes
    assert "TARGET_METADATA_INCOMPLETE" in codes


@pytest.mark.parametrize(
    "role",
    [
        "viewer",
        "template_author",
        "template_approver",
        "query_operator",
        "auditor",
    ],
)
def test_non_admin_roles_forbidden(
    db_session: Session, unauth_db_client: TestClient, role: str
) -> None:
    response = unauth_db_client.post(
        "/api/v1/connection-profiles",
        json=_create_body(environment=f"env-{role}"),
        headers=_headers(f"user-{role}", role),
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED


def test_missing_identity_401(unauth_db_client: TestClient) -> None:
    response = unauth_db_client.get("/api/v1/connection-profiles")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == AuthErrorCode.AUTHENTICATION_REQUIRED


def test_provider_disabled_503(
    monkeypatch: pytest.MonkeyPatch, test_settings_env: dict[str, str]
) -> None:
    monkeypatch.setenv("DQA_AUTH_PROVIDER", "disabled")
    from app.adapters.db.session import get_engine, get_session_factory
    from app.core.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    application = create_app(init_db_on_startup=False)
    with TestClient(application) as client:
        response = client.get(
            "/api/v1/connection-profiles",
            headers=_headers("admin", "administrator"),
        )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == AuthErrorCode.PROVIDER_NOT_CONFIGURED
    get_settings.cache_clear()


def test_connection_profile_manage_permission_mapping() -> None:
    assert Permission.CONNECTION_PROFILE_MANAGE in permissions_for_roles(
        {Role.ADMINISTRATOR}
    )
    for role in (
        Role.VIEWER,
        Role.TEMPLATE_AUTHOR,
        Role.TEMPLATE_APPROVER,
        Role.QUERY_OPERATOR,
        Role.AUDITOR,
    ):
        assert Permission.CONNECTION_PROFILE_MANAGE not in permissions_for_roles({role})


def test_no_delete_route(db_client: TestClient) -> None:
    created = db_client.post(
        "/api/v1/connection-profiles",
        json=_create_body(environment="nodelete"),
    )
    assert created.status_code == 201
    profile_id = created.json()["id"]
    deleted = db_client.delete(f"/api/v1/connection-profiles/{profile_id}")
    assert deleted.status_code == 405
