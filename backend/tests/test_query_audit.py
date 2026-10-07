"""Query Audit foundation tests (append-only writer + AUDIT_READ APIs)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.auth.errors import AuthErrorCode
from app.auth.models import Permission, Role
from app.auth.rbac import permissions_for_roles
from app.core.config import get_settings
from app.models.query_audit import QueryAuditEvent
from app.schemas.audit import QueryAuditEventCreate, new_audit_id
from app.services.query_audit import record_query_audit_event

pytestmark = pytest.mark.integration


def _headers(actor: str, roles: str) -> dict[str, str]:
    return {
        "X-DQA-Dev-Actor": actor,
        "X-DQA-Dev-Roles": roles,
    }


def _payload(**overrides: object) -> QueryAuditEventCreate:
    body: dict[str, object] = {
        "event_type": "QUERY_REQUEST",
        "status": "STARTED",
        "actor_id": "test-operator",
        "source_name": "oracle_demis_mock",
        "catalog_revision_id": 1,
        "catalog_fingerprint": "fp-audit",
        "template_id": 10,
        "template_version_id": 20,
        "connection_profile_id": 3,
        "parameter_names": ["ward_cd", "from_date"],
        "sensitive_parameter_names": ["ward_cd"],
    }
    body.update(overrides)
    return QueryAuditEventCreate.model_validate(body)


def test_alembic_chain_includes_audit_revision() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    rev = script.get_revision("20260929_audit01")
    assert rev is not None
    assert rev.down_revision == "20260929_cp01"
    hist = script.get_revision("20261007_hist01")
    assert hist is not None
    assert hist.down_revision == "20260929_audit01"
    heads = script.get_heads()
    assert list(heads) == ["20261007_hist01"]


def test_record_and_list_get_audit_events(
    db_session: Session, db_client: TestClient
) -> None:
    audit_id = new_audit_id()
    first = record_query_audit_event(
        db_session,
        _payload(audit_id=audit_id, status="STARTED"),
    )
    second = record_query_audit_event(
        db_session,
        _payload(
            audit_id=audit_id,
            event_type="QUERY_EXECUTION",
            status="SUCCEEDED",
            elapsed_ms=12,
            row_count=5,
            result_truncated=True,
        ),
    )
    db_session.commit()

    assert first.audit_id == audit_id
    assert first.parameter_logging_policy == "NAMES_ONLY"
    assert first.parameter_names == ["ward_cd", "from_date"]
    assert first.sensitive_parameter_names == ["ward_cd"]
    assert second.id > first.id
    assert second.result_truncated is True
    assert first.result_truncated is None

    listed = db_client.get("/api/v1/audit-events", params={"audit_id": audit_id})
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] == 2
    # created_at desc, id desc
    assert body["items"][0]["id"] == second.id
    assert body["items"][1]["id"] == first.id

    got = db_client.get(f"/api/v1/audit-events/{audit_id}")
    assert got.status_code == 200
    bundle = got.json()
    assert bundle["audit_id"] == audit_id
    assert len(bundle["items"]) == 2
    assert "password" not in got.text.casefold()
    assert "SELECT" not in got.text
    assert "request_text" not in got.text
    assert "A01" not in got.text  # no parameter values

    stored = db_session.scalars(
        select(QueryAuditEvent).where(QueryAuditEvent.audit_id == audit_id)
    ).all()
    assert len(stored) == 2
    for row in stored:
        assert isinstance(row.parameter_names, list)
        assert all(isinstance(name, str) for name in row.parameter_names)
        # Ensure no accidental value-shaped payloads
        assert row.parameter_names == ["ward_cd", "from_date"] or row.parameter_names == [
            "ward_cd",
            "from_date",
        ]


def test_filters_and_pagination(db_session: Session, db_client: TestClient) -> None:
    record_query_audit_event(
        db_session,
        _payload(audit_id=new_audit_id(), actor_id="a1", template_id=1, status="STARTED"),
    )
    record_query_audit_event(
        db_session,
        _payload(
            audit_id=new_audit_id(),
            actor_id="a2",
            template_id=2,
            event_type="QUERY_EXECUTION",
            status="FAILED",
            failure_category="SQL_TIMEOUT",
        ),
    )
    db_session.commit()

    filtered = db_client.get(
        "/api/v1/audit-events",
        params={"actor_id": "a2", "status": "FAILED", "event_type": "QUERY_EXECUTION"},
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["failure_category"] == "SQL_TIMEOUT"

    page = db_client.get("/api/v1/audit-events", params={"limit": 1, "offset": 0})
    assert page.status_code == 200
    assert len(page.json()["items"]) == 1
    assert page.json()["total"] >= 2


@pytest.mark.parametrize("role", ["auditor", "template_approver", "administrator"])
def test_audit_read_roles_allowed(
    db_session: Session, unauth_db_client: TestClient, role: str
) -> None:
    audit_id = new_audit_id()
    record_query_audit_event(db_session, _payload(audit_id=audit_id))
    db_session.commit()
    response = unauth_db_client.get(
        "/api/v1/audit-events",
        params={"audit_id": audit_id},
        headers=_headers(f"user-{role}", role),
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    "role",
    ["viewer", "template_author", "query_operator"],
)
def test_audit_read_roles_denied(
    db_session: Session, unauth_db_client: TestClient, role: str
) -> None:
    response = unauth_db_client.get(
        "/api/v1/audit-events",
        headers=_headers(f"user-{role}", role),
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED


def test_missing_identity_401(unauth_db_client: TestClient) -> None:
    response = unauth_db_client.get("/api/v1/audit-events")
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
            "/api/v1/audit-events",
            headers=_headers("auditor", "auditor"),
        )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == AuthErrorCode.PROVIDER_NOT_CONFIGURED
    get_settings.cache_clear()


def test_no_public_write_update_delete(db_client: TestClient) -> None:
    assert db_client.post("/api/v1/audit-events", json={}).status_code == 405
    assert db_client.patch("/api/v1/audit-events/x", json={}).status_code == 405
    assert db_client.delete("/api/v1/audit-events/x").status_code == 405


def test_create_schema_forbids_value_and_result_fields() -> None:
    with pytest.raises(ValidationError):
        QueryAuditEventCreate.model_validate(
            {
                "event_type": "QUERY_REQUEST",
                "status": "STARTED",
                "parameter_values": {"ward_cd": "A01"},
            }
        )
    with pytest.raises(ValidationError):
        QueryAuditEventCreate.model_validate(
            {
                "event_type": "QUERY_REQUEST",
                "status": "STARTED",
                "result_rows": [{"a": 1}],
            }
        )
    with pytest.raises(ValidationError):
        QueryAuditEventCreate.model_validate(
            {
                "event_type": "QUERY_REQUEST",
                "status": "STARTED",
                "sql_text": "SELECT 1",
            }
        )
    with pytest.raises(ValidationError):
        QueryAuditEventCreate.model_validate(
            {
                "event_type": "QUERY_REQUEST",
                "status": "STARTED",
                "request_text": "show wards",
            }
        )


def test_failure_category_sanitized(db_session: Session) -> None:
    with pytest.raises(ValidationError):
        _payload(failure_category="boom; DROP TABLE x")
    ok = record_query_audit_event(
        db_session,
        _payload(
            event_type="QUERY_EXECUTION",
            status="FAILED",
            failure_category="AUTHZ_DENIED",
        ),
    )
    assert ok.failure_category == "AUTHZ_DENIED"


def test_result_truncated_is_boolean_indicator_only() -> None:
    assert _payload(result_truncated=True).result_truncated is True
    assert _payload(result_truncated=False).result_truncated is False
    assert _payload(result_truncated=None).result_truncated is None
    with pytest.raises(ValidationError):
        _payload(result_truncated="TRUNCATED")
    with pytest.raises(ValidationError):
        _payload(result_truncated="true")


def test_unknown_event_type_rejected() -> None:
    with pytest.raises(ValidationError):
        QueryAuditEventCreate.model_validate(
            {"event_type": "CUSTOM", "status": "STARTED"}
        )


def test_audit_read_permission_mapping_unchanged() -> None:
    assert Permission.AUDIT_READ in permissions_for_roles({Role.AUDITOR})
    assert Permission.AUDIT_READ in permissions_for_roles({Role.TEMPLATE_APPROVER})
    assert Permission.AUDIT_READ in permissions_for_roles({Role.ADMINISTRATOR})
    assert Permission.AUDIT_READ not in permissions_for_roles({Role.QUERY_OPERATOR})
    assert Permission.AUDIT_READ not in permissions_for_roles({Role.VIEWER})


def test_migration_upgrade_chain(test_settings_env: dict[str, str]) -> None:
    """cp01 -> audit01 -> hist01 upgrade works when starting from stamped cp01."""
    from alembic import command
    from alembic.config import Config

    from app.adapters.db.session import get_engine

    get_settings.cache_clear()
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS query_audit_events CASCADE"))
        for name in (
            "query_template_review_events",
            "query_template_versions",
            "query_templates",
            "catalog_activation_events",
            "catalog_active_revisions",
            "catalog_import_revisions",
        ):
            conn.execute(text(f"DROP TABLE IF EXISTS {name} CASCADE"))
        # Ensure alembic_version exists and points at cp01 when table may already exist.
        if inspect(engine).has_table("alembic_version"):
            conn.execute(text("DELETE FROM alembic_version"))
            conn.execute(
                text("INSERT INTO alembic_version (version_num) VALUES ('20260929_cp01')")
            )
        else:
            conn.execute(
                text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
            )
            conn.execute(
                text("INSERT INTO alembic_version (version_num) VALUES ('20260929_cp01')")
            )

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    assert inspect(engine).has_table("query_audit_events")
    assert inspect(engine).has_table("catalog_import_revisions")
    assert inspect(engine).has_table("query_templates")
    with engine.begin() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert version == "20261007_hist01"
