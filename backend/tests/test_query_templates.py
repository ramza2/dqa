"""Draft Query Template registry integration tests."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.adapters.catalog.query_template_errors import QueryTemplateErrorCode
from app.models.catalog_import import CatalogImportRevision
from app.models.query_template import QueryTemplate, QueryTemplateVersion
from app.services.catalog_active import activate_catalog_revision
from app.services.catalog_package_import import import_catalog_package_bytes
from tests.catalog_package_fixtures import (
    DEFAULT_SOURCE,
    build_core_documents,
    build_package_zip,
)

pytestmark = pytest.mark.integration

SOURCE_A = dict(DEFAULT_SOURCE)


def _import_and_activate(
    session: Session,
    *,
    fingerprint: str,
    source: dict[str, Any] | None = None,
    tables: list[dict[str, Any]] | None = None,
) -> CatalogImportRevision:
    src = source or SOURCE_A
    files = build_core_documents(
        source=src,
        fingerprint=fingerprint,
        tables=tables
        if tables is not None
        else [
            {"schema": "DEMIS_OWNER", "name": "T1"},
            {"schema": "OTHER_OWNER", "name": "T2"},
        ],
    )
    archive = build_package_zip(
        package_readiness="READY",
        source=src,
        fingerprint=fingerprint,
        files=files,
    )
    revision, created = import_catalog_package_bytes(archive, session)
    assert created is True
    activate_catalog_revision(session, revision.id)
    session.flush()
    return revision


def _create_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "stable_key": "ward_lookup",
        "name": "Ward lookup draft",
        "description": "draft only",
        "source_name": SOURCE_A["source_name"],
        "target_schemas": ["DEMIS_OWNER"],
        "sql_text": "SELECT 1 FROM dual WHERE id = :ward_id",
        "parameter_schema": [
            {
                "name": "ward_id",
                "label": "Ward ID",
                "type": "integer",
                "required": True,
                "min": 1,
                "max": 9999,
            }
        ],
        "row_limit": 50,
        "timeout_seconds": 15,
    }
    body.update(overrides)
    return body


def test_create_template_pins_active_catalog_as_draft(
    db_session: Session, db_client: TestClient
) -> None:
    revision = _import_and_activate(db_session, fingerprint="fp-tpl-create")
    db_session.commit()

    response = db_client.post("/api/v1/query-templates", json=_create_body())
    assert response.status_code == 201, response.text
    payload = response.json()

    assert payload["stable_key"] == "ward_lookup"
    assert payload["enabled"] is False
    assert payload["source_name"] == SOURCE_A["source_name"]
    assert payload["current_version"] == 1
    assert payload["approval_status"] == "DRAFT"
    assert payload["version"]["version"] == 1
    assert payload["version"]["approval_status"] == "DRAFT"
    assert payload["version"]["compatibility"]["mode"] == "EXACT_FINGERPRINT"
    assert payload["version"]["compatibility"]["compatible"] is True
    assert payload["version"]["compatibility"]["pinned_revision_id"] == revision.id
    assert payload["version"]["compatibility"]["pinned_schema_fingerprint"] == "fp-tpl-create"
    assert payload["version"]["compatibility"]["current_revision_id"] == revision.id
    assert payload["version"]["parameter_schema"][0]["name"] == "ward_id"
    assert payload["version"]["row_limit"] == 50
    assert payload["version"]["timeout_seconds"] == 15


def test_parameter_schema_round_trip(db_session: Session, db_client: TestClient) -> None:
    _import_and_activate(db_session, fingerprint="fp-tpl-params")
    db_session.commit()

    params = [
        {
            "name": "status",
            "type": "enum",
            "required": True,
            "allowed_values": ["OPEN", "CLOSED"],
        },
        {
            "name": "codes",
            "type": "string_list",
            "required": False,
            "min_items": 0,
            "max_items": 5,
            "sensitive": True,
        },
    ]
    response = db_client.post(
        "/api/v1/query-templates",
        json=_create_body(stable_key="params_roundtrip", parameter_schema=params),
    )
    assert response.status_code == 201, response.text
    detail = db_client.get(f"/api/v1/query-templates/{response.json()['id']}")
    assert detail.status_code == 200
    stored = detail.json()["version"]["parameter_schema"]
    assert stored[0]["allowed_values"] == ["OPEN", "CLOSED"]
    assert stored[1]["sensitive"] is True
    assert stored[1]["max_items"] == 5


def test_duplicate_stable_key_rejected(db_session: Session, db_client: TestClient) -> None:
    _import_and_activate(db_session, fingerprint="fp-tpl-dup")
    db_session.commit()

    first = db_client.post("/api/v1/query-templates", json=_create_body())
    assert first.status_code == 201
    second = db_client.post("/api/v1/query-templates", json=_create_body())
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == QueryTemplateErrorCode.DUPLICATE_STABLE_KEY


def test_duplicate_parameter_name_rejected(db_session: Session, db_client: TestClient) -> None:
    _import_and_activate(db_session, fingerprint="fp-tpl-dup-param")
    db_session.commit()

    response = db_client.post(
        "/api/v1/query-templates",
        json=_create_body(
            parameter_schema=[
                {"name": "ward_id", "type": "integer", "required": True},
                {"name": "ward_id", "type": "string", "required": False},
            ]
        ),
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "parameter_schema",
    [
        [{"name": "n", "type": "integer", "min": 10, "max": 1}],
        [{"name": "codes", "type": "string_list", "min_items": 5, "max_items": 1}],
        [{"name": "status", "type": "enum", "allowed_values": []}],
        [{"name": "status", "type": "enum"}],
    ],
)
def test_invalid_parameter_constraints_rejected(
    db_session: Session,
    db_client: TestClient,
    parameter_schema: list[dict[str, Any]],
) -> None:
    _import_and_activate(db_session, fingerprint=f"fp-tpl-bad-{hash(str(parameter_schema)) % 10_000}")
    db_session.commit()

    response = db_client.post(
        "/api/v1/query-templates",
        json=_create_body(
            stable_key=f"bad_{hash(str(parameter_schema)) % 10_000}",
            parameter_schema=parameter_schema,
        ),
    )
    assert response.status_code == 422


def test_create_without_active_catalog_rejected(db_client: TestClient) -> None:
    response = db_client.post("/api/v1/query-templates", json=_create_body())
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == QueryTemplateErrorCode.ACTIVE_CATALOG_NOT_FOUND


def test_unknown_target_schema_rejected(db_session: Session, db_client: TestClient) -> None:
    _import_and_activate(db_session, fingerprint="fp-tpl-bad-schema")
    db_session.commit()

    response = db_client.post(
        "/api/v1/query-templates",
        json=_create_body(target_schemas=["DOES_NOT_EXIST"]),
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == QueryTemplateErrorCode.INVALID_TARGET_SCHEMA


def test_list_and_detail(db_session: Session, db_client: TestClient) -> None:
    _import_and_activate(db_session, fingerprint="fp-tpl-list")
    db_session.commit()

    created = db_client.post(
        "/api/v1/query-templates",
        json=_create_body(stable_key="list_one", name="List One"),
    )
    assert created.status_code == 201
    template_id = created.json()["id"]

    listed = db_client.get(
        "/api/v1/query-templates",
        params={"source_name": SOURCE_A["source_name"]},
    )
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] >= 1
    assert any(item["id"] == template_id for item in body["items"])

    detail = db_client.get(f"/api/v1/query-templates/{template_id}")
    assert detail.status_code == 200
    assert detail.json()["name"] == "List One"
    assert detail.json()["version"]["sql_text"].startswith("SELECT")


def test_draft_update_and_delete(db_session: Session, db_client: TestClient) -> None:
    _import_and_activate(db_session, fingerprint="fp-tpl-mut")
    db_session.commit()

    created = db_client.post("/api/v1/query-templates", json=_create_body(stable_key="mutable"))
    assert created.status_code == 201
    template_id = created.json()["id"]
    pinned_fp = created.json()["version"]["compatibility"]["pinned_schema_fingerprint"]
    pinned_rev = created.json()["version"]["compatibility"]["pinned_revision_id"]

    patched = db_client.patch(
        f"/api/v1/query-templates/{template_id}",
        json={
            "name": "Updated name",
            "sql_text": "SELECT 2 FROM dual",
            "row_limit": 10,
            "parameter_schema": [{"name": "x", "type": "string", "required": True}],
        },
    )
    assert patched.status_code == 200, patched.text
    payload = patched.json()
    assert payload["name"] == "Updated name"
    assert payload["version"]["sql_text"] == "SELECT 2 FROM dual"
    assert payload["version"]["row_limit"] == 10
    assert payload["version"]["compatibility"]["pinned_schema_fingerprint"] == pinned_fp
    assert payload["version"]["compatibility"]["pinned_revision_id"] == pinned_rev
    assert payload["enabled"] is False
    assert payload["approval_status"] == "DRAFT"

    deleted = db_client.delete(f"/api/v1/query-templates/{template_id}")
    assert deleted.status_code == 204
    missing = db_client.get(f"/api/v1/query-templates/{template_id}")
    assert missing.status_code == 404


def test_unknown_template_404(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/query-templates/999999")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == QueryTemplateErrorCode.TEMPLATE_NOT_FOUND


def test_active_catalog_change_keeps_pinned_fingerprint(
    db_session: Session, db_client: TestClient
) -> None:
    first = _import_and_activate(db_session, fingerprint="fp-tpl-old")
    db_session.commit()

    created = db_client.post(
        "/api/v1/query-templates",
        json=_create_body(stable_key="pin_check"),
    )
    assert created.status_code == 201
    template_id = created.json()["id"]
    assert created.json()["version"]["compatibility"]["compatible"] is True
    assert created.json()["version"]["compatibility"]["pinned_revision_id"] == first.id
    assert (
        created.json()["version"]["compatibility"]["pinned_schema_fingerprint"]
        == "fp-tpl-old"
    )

    second = _import_and_activate(db_session, fingerprint="fp-tpl-new")
    db_session.commit()

    detail = db_client.get(f"/api/v1/query-templates/{template_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["version"]["compatibility"]["compatible"] is False
    assert payload["version"]["compatibility"]["pinned_revision_id"] == first.id
    assert payload["version"]["compatibility"]["pinned_schema_fingerprint"] == "fp-tpl-old"
    assert payload["version"]["compatibility"]["current_revision_id"] == second.id
    assert payload["version"]["compatibility"]["current_schema_fingerprint"] == "fp-tpl-new"

    # Pinned values must not be rewritten in persistence either.
    version = db_session.get(QueryTemplateVersion, payload["version"]["id"])
    assert version is not None
    assert version.catalog_revision_id == first.id
    assert version.catalog_fingerprint_constraint == "fp-tpl-old"
    template = db_session.get(QueryTemplate, template_id)
    assert template is not None
    assert template.enabled is False


def test_blank_sql_rejected(db_session: Session, db_client: TestClient) -> None:
    _import_and_activate(db_session, fingerprint="fp-tpl-blank-sql")
    db_session.commit()
    response = db_client.post(
        "/api/v1/query-templates",
        json=_create_body(sql_text="   "),
    )
    assert response.status_code == 422
