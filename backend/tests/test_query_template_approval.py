"""Query Template approval workflow integration tests."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.adapters.catalog.query_template_errors import QueryTemplateErrorCode
from app.models.catalog_import import CatalogImportRevision
from app.models.query_template import QueryTemplate, QueryTemplateVersion
from app.repositories.query_template import QueryTemplateRepository
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
        "stable_key": "approval_tpl",
        "name": "Approval draft",
        "description": "workflow",
        "source_name": SOURCE_A["source_name"],
        "target_schemas": ["DEMIS_OWNER"],
        "sql_text": "SELECT 1 FROM dual WHERE id = :ward_id",
        "parameter_schema": [
            {"name": "ward_id", "type": "integer", "required": True, "min": 1, "max": 99}
        ],
        "row_limit": 50,
        "timeout_seconds": 15,
    }
    body.update(overrides)
    return body


def _create_template(db_session: Session, db_client: TestClient, **overrides: Any) -> dict[str, Any]:
    _import_and_activate(db_session, fingerprint=overrides.pop("fingerprint", "fp-appr-base"))
    db_session.commit()
    response = db_client.post("/api/v1/query-templates", json=_create_body(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def test_draft_to_in_review_and_approve(
    db_session: Session, db_client: TestClient
) -> None:
    created = _create_template(db_session, db_client, stable_key="flow_approve")
    template_id = created["id"]

    submitted = db_client.post(f"/api/v1/query-templates/{template_id}/submit-review", json={})
    assert submitted.status_code == 200
    assert submitted.json()["approval_status"] == "IN_REVIEW"
    assert submitted.json()["enabled"] is False

    approved = db_client.post(
        f"/api/v1/query-templates/{template_id}/approve",
        json={"note": "looks good"},
    )
    assert approved.status_code == 200
    payload = approved.json()
    assert payload["approval_status"] == "APPROVED"
    assert payload["enabled"] is False
    assert payload["version"]["approved_at"] is not None
    assert payload["version"]["approval_note"] == "looks good"


def test_direct_draft_to_approved_or_rejected_forbidden(
    db_session: Session, db_client: TestClient
) -> None:
    created = _create_template(db_session, db_client, stable_key="flow_direct")
    template_id = created["id"]

    approved = db_client.post(f"/api/v1/query-templates/{template_id}/approve", json={})
    assert approved.status_code == 409
    assert approved.json()["detail"]["code"] == QueryTemplateErrorCode.INVALID_TRANSITION

    rejected = db_client.post(
        f"/api/v1/query-templates/{template_id}/reject",
        json={"note": "nope"},
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == QueryTemplateErrorCode.INVALID_TRANSITION


def test_in_review_to_rejected(db_session: Session, db_client: TestClient) -> None:
    created = _create_template(db_session, db_client, stable_key="flow_reject")
    template_id = created["id"]
    assert db_client.post(f"/api/v1/query-templates/{template_id}/submit-review").status_code == 200

    rejected = db_client.post(
        f"/api/v1/query-templates/{template_id}/reject",
        json={"note": "needs rewrite"},
    )
    assert rejected.status_code == 200
    payload = rejected.json()
    assert payload["approval_status"] == "REJECTED"
    assert payload["version"]["approved_at"] is None
    assert payload["version"]["approval_note"] is None
    assert payload["enabled"] is False

    events = db_client.get(f"/api/v1/query-templates/{template_id}/review-events")
    assert events.status_code == 200
    notes = [item["note"] for item in events.json()["items"]]
    assert "needs rewrite" in notes


def test_terminal_transitions_rejected(db_session: Session, db_client: TestClient) -> None:
    created = _create_template(db_session, db_client, stable_key="flow_terminal")
    template_id = created["id"]
    assert db_client.post(f"/api/v1/query-templates/{template_id}/submit-review").status_code == 200
    assert db_client.post(f"/api/v1/query-templates/{template_id}/approve", json={}).status_code == 200

    again = db_client.post(f"/api/v1/query-templates/{template_id}/approve", json={})
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == QueryTemplateErrorCode.INVALID_TRANSITION

    to_review = db_client.post(f"/api/v1/query-templates/{template_id}/submit-review")
    assert to_review.status_code == 409


@pytest.mark.parametrize("status_name", ["IN_REVIEW", "APPROVED", "REJECTED"])
def test_non_draft_patch_rejected(
    db_session: Session, db_client: TestClient, status_name: str
) -> None:
    created = _create_template(
        db_session, db_client, stable_key=f"patch_{status_name.lower()}"
    )
    template_id = created["id"]
    assert db_client.post(f"/api/v1/query-templates/{template_id}/submit-review").status_code == 200
    if status_name == "APPROVED":
        assert (
            db_client.post(f"/api/v1/query-templates/{template_id}/approve", json={}).status_code
            == 200
        )
    elif status_name == "REJECTED":
        assert (
            db_client.post(
                f"/api/v1/query-templates/{template_id}/reject",
                json={"note": "no"},
            ).status_code
            == 200
        )

    patched = db_client.patch(
        f"/api/v1/query-templates/{template_id}",
        json={"sql_text": "SELECT 2 FROM dual"},
    )
    assert patched.status_code == 409
    assert patched.json()["detail"]["code"] == QueryTemplateErrorCode.NOT_DRAFT


def test_reviewed_template_delete_rejected(
    db_session: Session, db_client: TestClient
) -> None:
    created = _create_template(db_session, db_client, stable_key="del_reviewed")
    template_id = created["id"]
    assert db_client.post(f"/api/v1/query-templates/{template_id}/submit-review").status_code == 200
    deleted = db_client.delete(f"/api/v1/query-templates/{template_id}")
    assert deleted.status_code == 409
    assert deleted.json()["detail"]["code"] == QueryTemplateErrorCode.NOT_DRAFT


def test_new_version_from_approved_and_rejected(
    db_session: Session, db_client: TestClient
) -> None:
    created = _create_template(db_session, db_client, stable_key="new_from_approved")
    template_id = created["id"]
    v1_id = created["version"]["id"]
    assert db_client.post(f"/api/v1/query-templates/{template_id}/submit-review").status_code == 200
    assert db_client.post(f"/api/v1/query-templates/{template_id}/approve", json={}).status_code == 200

    created_v2 = db_client.post(
        f"/api/v1/query-templates/{template_id}/versions",
        json={"sql_text": "SELECT 2 FROM dual"},
    )
    assert created_v2.status_code == 201, created_v2.text
    payload = created_v2.json()
    assert payload["current_version"] == 2
    assert payload["approval_status"] == "DRAFT"
    assert payload["enabled"] is False
    assert payload["version"]["sql_text"] == "SELECT 2 FROM dual"

    v1 = db_session.get(QueryTemplateVersion, v1_id)
    assert v1 is not None
    assert v1.approval_status == "APPROVED"
    assert v1.sql_text.startswith("SELECT 1")

    # Rejected path
    created2 = _create_template(
        db_session, db_client, stable_key="new_from_rejected", fingerprint="fp-appr-rej"
    )
    tid2 = created2["id"]
    assert db_client.post(f"/api/v1/query-templates/{tid2}/submit-review").status_code == 200
    assert (
        db_client.post(
            f"/api/v1/query-templates/{tid2}/reject", json={"note": "bad"}
        ).status_code
        == 200
    )
    v2 = db_client.post(f"/api/v1/query-templates/{tid2}/versions", json={})
    assert v2.status_code == 201
    assert v2.json()["current_version"] == 2
    assert v2.json()["approval_status"] == "DRAFT"


def test_new_version_from_draft_or_in_review_rejected(
    db_session: Session, db_client: TestClient
) -> None:
    created = _create_template(db_session, db_client, stable_key="new_bad_state")
    template_id = created["id"]
    draft_new = db_client.post(f"/api/v1/query-templates/{template_id}/versions", json={})
    assert draft_new.status_code == 409
    assert draft_new.json()["detail"]["code"] == QueryTemplateErrorCode.INVALID_TRANSITION

    assert db_client.post(f"/api/v1/query-templates/{template_id}/submit-review").status_code == 200
    review_new = db_client.post(f"/api/v1/query-templates/{template_id}/versions", json={})
    assert review_new.status_code == 409


def test_new_version_repins_active_catalog(
    db_session: Session, db_client: TestClient
) -> None:
    first = _import_and_activate(db_session, fingerprint="fp-v1-pin")
    db_session.commit()
    created = db_client.post(
        "/api/v1/query-templates",
        json=_create_body(stable_key="repin"),
    )
    assert created.status_code == 201
    template_id = created["id"]
    v1_id = created["version"]["id"]
    assert created.json()["version"]["compatibility"]["pinned_revision_id"] == first.id

    assert db_client.post(f"/api/v1/query-templates/{template_id}/submit-review").status_code == 200
    assert db_client.post(f"/api/v1/query-templates/{template_id}/approve", json={}).status_code == 200

    second = _import_and_activate(db_session, fingerprint="fp-v2-pin")
    db_session.commit()

    created_v2 = db_client.post(f"/api/v1/query-templates/{template_id}/versions", json={})
    assert created_v2.status_code == 201
    payload = created_v2.json()
    assert payload["version"]["compatibility"]["pinned_revision_id"] == second.id
    assert payload["version"]["compatibility"]["pinned_schema_fingerprint"] == "fp-v2-pin"

    v1 = db_session.get(QueryTemplateVersion, v1_id)
    assert v1 is not None
    assert v1.catalog_revision_id == first.id
    assert v1.catalog_fingerprint_constraint == "fp-v1-pin"


def test_new_version_rejects_missing_target_schema_on_new_active(
    db_session: Session, db_client: TestClient
) -> None:
    _import_and_activate(
        db_session,
        fingerprint="fp-old-schemas",
        tables=[
            {"schema": "DEMIS_OWNER", "name": "T1"},
            {"schema": "OTHER_OWNER", "name": "T2"},
        ],
    )
    db_session.commit()
    created = db_client.post(
        "/api/v1/query-templates",
        json=_create_body(stable_key="missing_schema", target_schemas=["OTHER_OWNER"]),
    )
    assert created.status_code == 201
    template_id = created["id"]
    assert db_client.post(f"/api/v1/query-templates/{template_id}/submit-review").status_code == 200
    assert db_client.post(f"/api/v1/query-templates/{template_id}/approve", json={}).status_code == 200

    _import_and_activate(
        db_session,
        fingerprint="fp-new-no-other",
        tables=[{"schema": "DEMIS_OWNER", "name": "T1"}],
    )
    db_session.commit()

    created_v2 = db_client.post(f"/api/v1/query-templates/{template_id}/versions", json={})
    assert created_v2.status_code == 422
    assert created_v2.json()["detail"]["code"] == QueryTemplateErrorCode.INVALID_TARGET_SCHEMA


def test_review_and_version_history(db_session: Session, db_client: TestClient) -> None:
    created = _create_template(db_session, db_client, stable_key="history")
    template_id = created["id"]
    assert db_client.post(f"/api/v1/query-templates/{template_id}/submit-review").status_code == 200
    assert db_client.post(f"/api/v1/query-templates/{template_id}/approve", json={}).status_code == 200
    assert db_client.post(f"/api/v1/query-templates/{template_id}/versions", json={}).status_code == 201

    events = db_client.get(f"/api/v1/query-templates/{template_id}/review-events")
    assert events.status_code == 200
    items = events.json()["items"]
    assert len(items) == 2
    assert items[0]["from_status"] == "DRAFT"
    assert items[0]["to_status"] == "IN_REVIEW"
    assert items[1]["from_status"] == "IN_REVIEW"
    assert items[1]["to_status"] == "APPROVED"
    assert items[0]["id"] < items[1]["id"]

    versions = db_client.get(f"/api/v1/query-templates/{template_id}/versions")
    assert versions.status_code == 200
    v_items = versions.json()["items"]
    assert [item["version"] for item in v_items] == [1, 2]
    assert v_items[0]["approval_status"] == "APPROVED"
    assert v_items[1]["approval_status"] == "DRAFT"


def test_stable_metadata_freeze_after_review(
    db_session: Session, db_client: TestClient
) -> None:
    created = _create_template(db_session, db_client, stable_key="freeze")
    template_id = created["id"]

    # Pure DRAFT: stable metadata editable.
    patched = db_client.patch(
        f"/api/v1/query-templates/{template_id}",
        json={"name": "Renamed", "description": "updated", "target_schemas": ["OTHER_OWNER"]},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Renamed"

    assert db_client.post(f"/api/v1/query-templates/{template_id}/submit-review").status_code == 200
    assert db_client.post(f"/api/v1/query-templates/{template_id}/approve", json={}).status_code == 200
    assert db_client.post(f"/api/v1/query-templates/{template_id}/versions", json={}).status_code == 201

    frozen = db_client.patch(
        f"/api/v1/query-templates/{template_id}",
        json={"name": "Should fail"},
    )
    assert frozen.status_code == 409
    assert frozen.json()["detail"]["code"] == QueryTemplateErrorCode.STABLE_METADATA_FROZEN

    # Version authoring still allowed on new DRAFT.
    authoring = db_client.patch(
        f"/api/v1/query-templates/{template_id}",
        json={
            "sql_text": "SELECT 9 FROM dual",
            "row_limit": 7,
            "timeout_seconds": 9,
            "parameter_schema": [{"name": "x", "type": "string", "required": True}],
        },
    )
    assert authoring.status_code == 200, authoring.text
    assert authoring.json()["version"]["sql_text"] == "SELECT 9 FROM dual"
    assert authoring.json()["version"]["row_limit"] == 7
    assert authoring.json()["name"] == "Renamed"


def test_enable_disable_rules(db_session: Session, db_client: TestClient) -> None:
    created = _create_template(db_session, db_client, stable_key="enable_rules")
    template_id = created["id"]

    draft_enable = db_client.post(f"/api/v1/query-templates/{template_id}/enable")
    assert draft_enable.status_code == 409

    assert db_client.post(f"/api/v1/query-templates/{template_id}/submit-review").status_code == 200
    review_enable = db_client.post(f"/api/v1/query-templates/{template_id}/enable")
    assert review_enable.status_code == 409

    approved = db_client.post(f"/api/v1/query-templates/{template_id}/approve", json={})
    assert approved.status_code == 200
    assert approved.json()["enabled"] is False

    enabled = db_client.post(f"/api/v1/query-templates/{template_id}/enable")
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True

    again = db_client.post(f"/api/v1/query-templates/{template_id}/enable")
    assert again.status_code == 200
    assert again.json()["enabled"] is True

    disabled = db_client.post(f"/api/v1/query-templates/{template_id}/disable")
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    again_disable = db_client.post(f"/api/v1/query-templates/{template_id}/disable")
    assert again_disable.status_code == 200
    assert again_disable.json()["enabled"] is False


def test_enable_rejected_when_incompatible(
    db_session: Session, db_client: TestClient
) -> None:
    first = _import_and_activate(db_session, fingerprint="fp-en-old")
    db_session.commit()
    created = db_client.post(
        "/api/v1/query-templates",
        json=_create_body(stable_key="enable_incompat"),
    )
    assert created.status_code == 201
    template_id = created["id"]
    assert created.json()["version"]["compatibility"]["pinned_revision_id"] == first.id
    assert db_client.post(f"/api/v1/query-templates/{template_id}/submit-review").status_code == 200
    assert db_client.post(f"/api/v1/query-templates/{template_id}/approve", json={}).status_code == 200

    _import_and_activate(db_session, fingerprint="fp-en-new")
    db_session.commit()

    enabled = db_client.post(f"/api/v1/query-templates/{template_id}/enable")
    assert enabled.status_code == 409
    assert enabled.json()["detail"]["code"] == QueryTemplateErrorCode.INCOMPATIBLE_CATALOG


def test_enabled_not_auto_rewritten_when_catalog_changes(
    db_session: Session, db_client: TestClient
) -> None:
    _import_and_activate(db_session, fingerprint="fp-en-keep")
    db_session.commit()
    created = db_client.post(
        "/api/v1/query-templates",
        json=_create_body(stable_key="enable_keep"),
    )
    template_id = created["id"]
    assert db_client.post(f"/api/v1/query-templates/{template_id}/submit-review").status_code == 200
    assert db_client.post(f"/api/v1/query-templates/{template_id}/approve", json={}).status_code == 200
    assert db_client.post(f"/api/v1/query-templates/{template_id}/enable").status_code == 200

    _import_and_activate(db_session, fingerprint="fp-en-changed")
    db_session.commit()

    detail = db_client.get(f"/api/v1/query-templates/{template_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["enabled"] is True
    assert payload["version"]["compatibility"]["compatible"] is False


def test_reject_requires_note(db_session: Session, db_client: TestClient) -> None:
    created = _create_template(db_session, db_client, stable_key="reject_note")
    template_id = created["id"]
    assert db_client.post(f"/api/v1/query-templates/{template_id}/submit-review").status_code == 200
    missing = db_client.post(f"/api/v1/query-templates/{template_id}/reject", json={"note": "  "})
    assert missing.status_code == 422


def test_lifecycle_uses_for_update_path(db_session: Session) -> None:
    """Structural check: repository exposes FOR UPDATE locking for lifecycle races."""
    repo = QueryTemplateRepository(db_session)
    assert hasattr(repo, "get_by_id_for_update")
    assert callable(repo.get_by_id_for_update)
