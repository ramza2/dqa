"""Authentication and RBAC API integration tests."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.errors import AuthErrorCode
from app.auth.models import Role
from app.core.config import Settings
from app.services.catalog_active import activate_catalog_revision
from app.services.catalog_package_import import import_catalog_package_bytes
from tests.catalog_package_fixtures import (
    DEFAULT_SOURCE,
    build_core_documents,
    build_package_zip,
)

pytestmark = pytest.mark.integration

SOURCE = dict(DEFAULT_SOURCE)


def _headers(actor: str, roles: str) -> dict[str, str]:
    return {
        "X-DQA-Dev-Actor": actor,
        "X-DQA-Dev-Roles": roles,
    }


def _import_and_activate(session: Session, *, fingerprint: str = "fp-auth") -> None:
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


def _create_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "stable_key": "auth.tpl",
        "name": "auth template",
        "description": "auth test",
        "source_name": SOURCE["source_name"],
        "target_schemas": ["DEMIS_OWNER"],
        "sql_text": "SELECT 1 FROM dual",
        "parameter_schema": [],
        "row_limit": 50,
        "timeout_seconds": 15,
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# Authentication fail-closed
# ---------------------------------------------------------------------------


def test_provider_disabled_returns_503(
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
            "/api/v1/query-templates",
            headers=_headers("anyone", "administrator"),
        )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == AuthErrorCode.PROVIDER_NOT_CONFIGURED
    get_settings.cache_clear()


def test_dev_headers_blocked_in_production(
    monkeypatch: pytest.MonkeyPatch, test_settings_env: dict[str, str]
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DQA_AUTH_PROVIDER", "dev_headers")
    from app.adapters.db.session import get_engine, get_session_factory
    from app.core.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    application = create_app(init_db_on_startup=False)
    with TestClient(application) as client:
        response = client.get(
            "/api/v1/query-templates",
            headers=_headers("anyone", "administrator"),
        )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == AuthErrorCode.PROVIDER_UNAVAILABLE
    get_settings.cache_clear()


def test_missing_actor_returns_401(unauth_client: TestClient) -> None:
    response = unauth_client.get("/api/v1/query-templates")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == AuthErrorCode.AUTHENTICATION_REQUIRED


def test_blank_actor_returns_401(unauth_client: TestClient) -> None:
    response = unauth_client.get(
        "/api/v1/query-templates",
        headers={"X-DQA-Dev-Actor": "   ", "X-DQA-Dev-Roles": "viewer"},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == AuthErrorCode.AUTHENTICATION_INVALID


def test_unknown_role_returns_401(unauth_client: TestClient) -> None:
    response = unauth_client.get(
        "/api/v1/query-templates",
        headers=_headers("u1", "not_a_real_role"),
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == AuthErrorCode.AUTHENTICATION_INVALID


def test_duplicate_roles_deduped(unauth_client: TestClient) -> None:
    response = unauth_client.get(
        "/api/v1/auth/me",
        headers=_headers("u1", "viewer,viewer,template_author"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["actor_id"] == "u1"
    assert body["roles"] == ["template_author", "viewer"]
    assert body["provider"] == "dev_headers"


def test_authenticated_without_permission_returns_403(unauth_client: TestClient) -> None:
    response = unauth_client.get(
        "/api/v1/query-templates",
        headers=_headers("ops", "query_operator"),
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED


def test_health_unauthenticated(unauth_client: TestClient) -> None:
    assert unauth_client.get("/health").status_code == 200
    assert unauth_client.get("/health/ready").status_code == 200


# ---------------------------------------------------------------------------
# RBAC endpoint matrix
# ---------------------------------------------------------------------------


def test_template_author_allowed_and_denied(
    db_session: Session, unauth_db_client: TestClient
) -> None:
    _import_and_activate(db_session, fingerprint="fp-author")
    db_session.commit()
    author = _headers("test-author", "template_author")

    created = unauth_db_client.post(
        "/api/v1/query-templates", json=_create_body(stable_key="auth_author"), headers=author
    )
    assert created.status_code == 201, created.text
    template_id = created.json()["id"]
    assert created.json()["version"]["created_by"] == "test-author"

    assert (
        unauth_db_client.patch(
            f"/api/v1/query-templates/{template_id}",
            json={"description": "updated"},
            headers=author,
        ).status_code
        == 200
    )
    assert (
        unauth_db_client.post(
            f"/api/v1/query-templates/{template_id}/submit-review",
            json={},
            headers=author,
        ).status_code
        == 200
    )
    assert (
        unauth_db_client.post(
            f"/api/v1/query-templates/{template_id}/approve",
            json={},
            headers=author,
        ).status_code
        == 403
    )
    assert (
        unauth_db_client.post(
            f"/api/v1/query-templates/{template_id}/enable",
            headers=author,
        ).status_code
        == 403
    )


def test_template_approver_allowed_and_denied(
    db_session: Session, unauth_db_client: TestClient
) -> None:
    _import_and_activate(db_session, fingerprint="fp-approver")
    db_session.commit()
    author = _headers("test-author", "template_author")
    approver = _headers("test-approver", "template_approver")

    created = unauth_db_client.post(
        "/api/v1/query-templates",
        json=_create_body(stable_key="auth_approver"),
        headers=author,
    )
    assert created.status_code == 201
    template_id = created.json()["id"]
    assert (
        unauth_db_client.post(
            f"/api/v1/query-templates/{template_id}/submit-review",
            json={},
            headers=author,
        ).status_code
        == 200
    )

    assert (
        unauth_db_client.post(
            "/api/v1/query-templates",
            json=_create_body(stable_key="auth_approver_denied"),
            headers=approver,
        ).status_code
        == 403
    )
    approved = unauth_db_client.post(
        f"/api/v1/query-templates/{template_id}/approve",
        json={},
        headers=approver,
    )
    assert approved.status_code == 200
    assert approved.json()["version"]["approved_by"] == "test-approver"
    assert (
        unauth_db_client.post(
            f"/api/v1/query-templates/{template_id}/enable",
            headers=approver,
        ).status_code
        == 200
    )
    assert (
        unauth_db_client.get(
            f"/api/v1/query-templates/{template_id}/review-events",
            headers=approver,
        ).status_code
        == 200
    )


def test_actor_propagation_on_lifecycle(
    db_session: Session, unauth_db_client: TestClient
) -> None:
    _import_and_activate(db_session, fingerprint="fp-actor")
    db_session.commit()
    author = _headers("test-author", "template_author")
    approver = _headers("test-approver", "template_approver")

    created = unauth_db_client.post(
        "/api/v1/query-templates",
        json=_create_body(stable_key="auth_actor_flow"),
        headers=author,
    )
    assert created.status_code == 201
    template_id = created.json()["id"]
    assert created.json()["version"]["created_by"] == "test-author"

    submitted = unauth_db_client.post(
        f"/api/v1/query-templates/{template_id}/submit-review",
        json={},
        headers=author,
    )
    assert submitted.status_code == 200
    events = unauth_db_client.get(
        f"/api/v1/query-templates/{template_id}/review-events",
        headers=approver,
    )
    assert events.status_code == 200
    submit_events = [
        item for item in events.json()["items"] if item["to_status"] == "IN_REVIEW"
    ]
    assert submit_events
    assert submit_events[0]["actor"] == "test-author"

    approved = unauth_db_client.post(
        f"/api/v1/query-templates/{template_id}/approve",
        json={},
        headers=approver,
    )
    assert approved.status_code == 200
    assert approved.json()["version"]["approved_by"] == "test-approver"
    events2 = unauth_db_client.get(
        f"/api/v1/query-templates/{template_id}/review-events",
        headers=approver,
    ).json()["items"]
    approve_events = [item for item in events2 if item["to_status"] == "APPROVED"]
    assert approve_events
    assert approve_events[0]["actor"] == "test-approver"

    new_version = unauth_db_client.post(
        f"/api/v1/query-templates/{template_id}/versions",
        json={},
        headers=author,
    )
    assert new_version.status_code == 201
    assert new_version.json()["version"]["created_by"] == "test-author"


def test_query_operator_allowed_and_template_mutation_denied(
    db_session: Session, unauth_db_client: TestClient
) -> None:
    _import_and_activate(db_session, fingerprint="fp-ops")
    db_session.commit()
    ops = _headers("ops", "query_operator")
    assert (
        unauth_db_client.post(
            "/api/v1/query-templates",
            json=_create_body(stable_key="ops_denied"),
            headers=ops,
        ).status_code
        == 403
    )
    # Recommendation without eligible templates still requires QUERY_OPERATE.
    response = unauth_db_client.post(
        "/api/v1/query-recommendations",
        json={
            "source_name": SOURCE["source_name"],
            "request_text": "병동 이력 조회",
        },
        headers=ops,
    )
    assert response.status_code in {200, 503}
    assert response.status_code != 403


def test_auditor_read_allowed_mutation_denied(
    db_session: Session, unauth_db_client: TestClient
) -> None:
    _import_and_activate(db_session, fingerprint="fp-auditor")
    db_session.commit()
    author = _headers("test-author", "template_author")
    auditor = _headers("auditor", "auditor")
    created = unauth_db_client.post(
        "/api/v1/query-templates",
        json=_create_body(stable_key="auth_auditor"),
        headers=author,
    )
    assert created.status_code == 201
    template_id = created.json()["id"]
    assert (
        unauth_db_client.get(
            f"/api/v1/query-templates/{template_id}",
            headers=auditor,
        ).status_code
        == 200
    )
    assert (
        unauth_db_client.get(
            f"/api/v1/query-templates/{template_id}/review-events",
            headers=auditor,
        ).status_code
        == 200
    )
    assert (
        unauth_db_client.post(
            f"/api/v1/query-templates/{template_id}/approve",
            json={},
            headers=auditor,
        ).status_code
        == 403
    )
    assert (
        unauth_db_client.post(
            "/api/v1/query-recommendations",
            json={
                "source_name": SOURCE["source_name"],
                "request_text": "병동",
            },
            headers=auditor,
        ).status_code
        == 403
    )


def test_administrator_can_access_protected_endpoints(
    db_session: Session, db_client: TestClient
) -> None:
    _import_and_activate(db_session, fingerprint="fp-admin")
    db_session.commit()
    created = db_client.post(
        "/api/v1/query-templates",
        json=_create_body(stable_key="auth_admin"),
    )
    assert created.status_code == 201
    template_id = created.json()["id"]
    assert db_client.get(f"/api/v1/query-templates/{template_id}").status_code == 200
    assert db_client.get("/api/v1/auth/me").status_code == 200
    me = db_client.get("/api/v1/auth/me").json()
    assert me["actor_id"] == "test-admin"
    assert Role.ADMINISTRATOR.value in me["roles"]


def test_settings_auth_provider_default_disabled() -> None:
    settings = Settings(
        APP_ENV="development",
        DQA_DB_HOST="localhost",
        DQA_DB_PORT=5432,
        DQA_DB_NAME="dqa",
        DQA_DB_USER="dqa",
        DQA_DB_PASSWORD="change-me",
    )
    assert settings.dqa_auth_provider == "disabled"
