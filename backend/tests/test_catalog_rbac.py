"""Catalog API RBAC hardening regression tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.errors import AuthErrorCode
from app.services.catalog_active import activate_catalog_revision
from app.services.catalog_package_import import import_catalog_package_bytes
from tests.catalog_package_fixtures import (
    DEFAULT_SOURCE,
    build_core_documents,
    build_package_zip,
)

pytestmark = pytest.mark.integration

SOURCE = dict(DEFAULT_SOURCE)
SOURCE_NAME = SOURCE["source_name"]


def _headers(actor: str, roles: str) -> dict[str, str]:
    return {
        "X-DQA-Dev-Actor": actor,
        "X-DQA-Dev-Roles": roles,
    }


def _seed_active_catalog(session: Session, *, fingerprint: str = "fp-catalog-rbac") -> int:
    files = build_core_documents(
        source=SOURCE,
        fingerprint=fingerprint,
        tables=[{"schema": "DEMIS_OWNER", "name": "T1"}],
        columns=[{"table": "T1", "name": "ID"}],
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


def _ready_zip(*, fingerprint: str = "fp-catalog-rbac-upload") -> bytes:
    return build_package_zip(
        package_readiness="READY",
        source=SOURCE,
        fingerprint=fingerprint,
        files=build_core_documents(source=SOURCE, fingerprint=fingerprint),
    )


# ---------------------------------------------------------------------------
# CATALOG_READ
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role",
    ["viewer", "query_operator", "auditor", "administrator", "template_author"],
)
def test_catalog_read_allowed_roles(
    db_session: Session, unauth_db_client: TestClient, role: str
) -> None:
    _seed_active_catalog(db_session, fingerprint=f"fp-read-{role}")
    db_session.commit()
    headers = _headers(f"actor-{role}", role)

    listed = unauth_db_client.get("/api/v1/catalog/active", headers=headers)
    assert listed.status_code == 200, listed.text
    assert any(item["source_name"] == SOURCE_NAME for item in listed.json())

    active = unauth_db_client.get(f"/api/v1/catalog/active/{SOURCE_NAME}", headers=headers)
    assert active.status_code == 200, active.text

    tables = unauth_db_client.get(
        f"/api/v1/catalog/active/{SOURCE_NAME}/tables",
        headers=headers,
    )
    assert tables.status_code == 200, tables.text
    assert tables.json()["total"] >= 1

    imports = unauth_db_client.get("/api/v1/catalog/imports", headers=headers)
    assert imports.status_code == 200, imports.text

    activations = unauth_db_client.get("/api/v1/catalog/activations", headers=headers)
    assert activations.status_code == 200, activations.text


def test_catalog_read_denied_without_roles(
    db_session: Session, unauth_db_client: TestClient
) -> None:
    _seed_active_catalog(db_session, fingerprint="fp-read-norole")
    db_session.commit()
    headers = _headers("no-perms", "")

    response = unauth_db_client.get("/api/v1/catalog/active", headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED

    tables = unauth_db_client.get(
        f"/api/v1/catalog/active/{SOURCE_NAME}/tables",
        headers=headers,
    )
    assert tables.status_code == 403
    assert tables.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED


def test_query_operator_source_discovery_and_manage_denied(
    db_session: Session, unauth_db_client: TestClient
) -> None:
    """Query Assistant needs active Catalog discovery via query_operator + CATALOG_READ."""
    revision_id = _seed_active_catalog(db_session, fingerprint="fp-ops-discovery")
    db_session.commit()
    ops = _headers("ops", "query_operator")

    listed = unauth_db_client.get("/api/v1/catalog/active", headers=ops)
    assert listed.status_code == 200
    assert any(item["source_name"] == SOURCE_NAME for item in listed.json())

    detail = unauth_db_client.get(f"/api/v1/catalog/active/{SOURCE_NAME}", headers=ops)
    assert detail.status_code == 200
    assert detail.json()["schema_fingerprint"] == "fp-ops-discovery"

    tables = unauth_db_client.get(
        f"/api/v1/catalog/active/{SOURCE_NAME}/tables",
        headers=ops,
    )
    assert tables.status_code == 200

    archive = _ready_zip(fingerprint="fp-ops-denied-upload")
    validate = unauth_db_client.post(
        "/api/v1/catalog/packages/validate",
        files={"file": ("pkg.zip", archive, "application/zip")},
        headers=ops,
    )
    assert validate.status_code == 403
    assert validate.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED

    imported = unauth_db_client.post(
        "/api/v1/catalog/packages/import",
        files={"file": ("pkg.zip", archive, "application/zip")},
        headers=ops,
    )
    assert imported.status_code == 403
    assert imported.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED

    activate = unauth_db_client.post(
        f"/api/v1/catalog/imports/{revision_id}/activate",
        headers=ops,
    )
    assert activate.status_code == 403
    assert activate.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED


# ---------------------------------------------------------------------------
# CATALOG_MANAGE
# ---------------------------------------------------------------------------


def test_administrator_catalog_manage_allowed(
    db_session: Session, unauth_db_client: TestClient
) -> None:
    db_session.commit()
    admin = _headers("admin", "administrator")
    archive = _ready_zip(fingerprint="fp-admin-manage")

    validate = unauth_db_client.post(
        "/api/v1/catalog/packages/validate",
        files={"file": ("pkg.zip", archive, "application/zip")},
        headers=admin,
    )
    assert validate.status_code == 200, validate.text
    assert validate.json()["valid"] is True

    imported = unauth_db_client.post(
        "/api/v1/catalog/packages/import",
        files={"file": ("pkg.zip", archive, "application/zip")},
        headers=admin,
    )
    assert imported.status_code == 200, imported.text
    revision_id = imported.json()["id"]

    activate = unauth_db_client.post(
        f"/api/v1/catalog/imports/{revision_id}/activate",
        headers=admin,
    )
    assert activate.status_code == 200, activate.text


@pytest.mark.parametrize(
    "role",
    ["viewer", "query_operator", "template_author", "template_approver", "auditor"],
)
def test_catalog_manage_denied_for_non_admin_roles(
    db_session: Session, unauth_db_client: TestClient, role: str
) -> None:
    revision_id = _seed_active_catalog(db_session, fingerprint=f"fp-manage-deny-{role}")
    db_session.commit()
    headers = _headers(f"actor-{role}", role)
    archive = _ready_zip(fingerprint=f"fp-manage-upload-{role}")

    validate = unauth_db_client.post(
        "/api/v1/catalog/packages/validate",
        files={"file": ("pkg.zip", archive, "application/zip")},
        headers=headers,
    )
    assert validate.status_code == 403
    assert validate.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED

    imported = unauth_db_client.post(
        "/api/v1/catalog/packages/import",
        files={"file": ("pkg.zip", archive, "application/zip")},
        headers=headers,
    )
    assert imported.status_code == 403
    assert imported.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED

    activate = unauth_db_client.post(
        f"/api/v1/catalog/imports/{revision_id}/activate",
        headers=headers,
    )
    assert activate.status_code == 403
    assert activate.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED


# ---------------------------------------------------------------------------
# Fail-closed provider / identity cases
# ---------------------------------------------------------------------------


def test_catalog_missing_identity_returns_401(unauth_db_client: TestClient) -> None:
    response = unauth_db_client.get("/api/v1/catalog/active")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == AuthErrorCode.AUTHENTICATION_REQUIRED

    validate = unauth_db_client.post(
        "/api/v1/catalog/packages/validate",
        files={"file": ("pkg.zip", _ready_zip(), "application/zip")},
    )
    assert validate.status_code == 401
    assert validate.json()["detail"]["code"] == AuthErrorCode.AUTHENTICATION_REQUIRED


def test_catalog_disabled_provider_returns_503(
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
            "/api/v1/catalog/active",
            headers=_headers("anyone", "administrator"),
        )
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == AuthErrorCode.PROVIDER_NOT_CONFIGURED

        manage = client.post(
            "/api/v1/catalog/packages/validate",
            files={"file": ("pkg.zip", _ready_zip(), "application/zip")},
            headers=_headers("anyone", "administrator"),
        )
        assert manage.status_code == 503
        assert manage.json()["detail"]["code"] == AuthErrorCode.PROVIDER_NOT_CONFIGURED
    get_settings.cache_clear()


def test_catalog_unknown_role_fail_closed(unauth_db_client: TestClient) -> None:
    response = unauth_db_client.get(
        "/api/v1/catalog/active",
        headers=_headers("bad-role", "not_a_real_role"),
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == AuthErrorCode.AUTHENTICATION_INVALID
