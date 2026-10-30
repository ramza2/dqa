"""M5-S1A service-client policy draft lifecycle and fail-closed API tests."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.service_client_draft import ServiceClientDraft, ServiceClientDraftEvent

pytestmark = pytest.mark.integration
PATH = "/api/v1/admin/service-clients"


@pytest.fixture()
def tracked_drafts(db_session: Session):
    ids: list[int] = []
    yield ids
    # Clean only records created by these tests, never unrelated operator data.
    db_session.rollback()
    if ids:
        db_session.execute(
            delete(ServiceClientDraftEvent).where(ServiceClientDraftEvent.client_draft_id.in_(ids))
        )
        db_session.execute(delete(ServiceClientDraft).where(ServiceClientDraft.id.in_(ids)))
        db_session.commit()


def _body() -> dict:
    return {
        "client_id": "m5-test-" + uuid4().hex[:18],
        "service_name": "FHIR adapter candidate",
        "organization": "Consortium (unapproved)",
        "owner_contact": "integration-team",
        "purpose": "metadata-only interface planning",
        "environment": "development",
        "requested_scopes": ["catalog:read"],
        "proposed_ip_cidrs": ["10.1.2.29/24", "2001:db8::1/64"],
    }


def _register(client: TestClient, tracked: list[int]) -> dict:
    response = client.post(PATH, json=_body())
    assert response.status_code == 201, response.text
    row = response.json()
    tracked.append(row["id"])
    return row


def test_draft_crud_audit_and_revocation_are_never_authorization(
    db_client: TestClient, db_session: Session, tracked_drafts: list[int],
) -> None:
    row = _register(db_client, tracked_drafts)
    draft_id = row["id"]
    assert row["status"] == "DRAFT"
    assert row["authentication_enabled"] is False
    assert row["external_access_allowed"] is False
    assert row["proposed_ip_cidrs"] == ["10.1.2.0/24", "2001:db8::/64"]
    assert "secret" not in row and "api_key" not in row

    listed = db_client.get(PATH)
    assert listed.status_code == 200
    assert any(item["id"] == draft_id for item in listed.json()["items"])

    got = db_client.get(f"{PATH}/{draft_id}")
    assert got.status_code == 200

    changed = db_client.patch(
        f"{PATH}/{draft_id}",
        json={"requested_scopes": ["mcp:read"], "proposed_ip_cidrs": ["192.0.2.4/32"]},
    )
    assert changed.status_code == 200
    assert changed.json()["requested_scopes"] == ["mcp:read"]
    assert changed.json()["external_access_allowed"] is False

    revoked = db_client.post(f"{PATH}/{draft_id}/revoke")
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "REVOKED"
    assert revoked.json()["authentication_enabled"] is False
    assert db_client.patch(f"{PATH}/{draft_id}", json={"purpose": "after revoke"}).status_code == 409
    assert db_client.post(f"{PATH}/{draft_id}/revoke").status_code == 409

    events = db_client.get(f"{PATH}/{draft_id}/events")
    assert events.status_code == 200
    assert [event["action"] for event in events.json()] == ["REVOKED", "UPDATED", "CREATED"]
    assert all(event["actor_id"] == "test-admin" for event in events.json())
    assert all(len(event["policy_sha256"]) == 64 for event in events.json())
    assert all("credential" not in str(event).lower() for event in events.json())

    persisted = db_session.scalar(select(ServiceClientDraft).where(ServiceClientDraft.id == draft_id))
    assert persisted is not None and persisted.status == "REVOKED"


def test_invalid_input_no_secret_echo_and_no_authority(
    db_client: TestClient, tracked_drafts: list[int],
) -> None:
    body = _body()
    for override in (
        {"api_key": "super-sensitive-value"},
        {"enabled": True},
        {"status": "ACTIVE"},
        {"requested_scopes": ["query:read", "query:read"]},
        {"proposed_ip_cidrs": ["0.0.0.0/0"]},
        {"proposed_ip_cidrs": ["not-an-ip-secret"]},
    ):
        response = db_client.post(PATH, json={**body, **override})
        assert response.status_code == 422, response.text
        assert "super-sensitive-value" not in response.text
        assert "not-an-ip-secret" not in response.text

    row = _register(db_client, tracked_drafts)
    bad_patch = db_client.patch(
        f"{PATH}/{row['id']}", json={"service_key": "invisible-sensitive-value"}
    )
    assert bad_patch.status_code == 422
    assert "invisible-sensitive-value" not in bad_patch.text
    assert db_client.patch(f"{PATH}/{row['id']}", json={}).status_code == 422
    assert db_client.post(f"{PATH}/{row['id']}/enable").status_code == 404
    assert db_client.delete(f"{PATH}/{row['id']}").status_code == 405


def test_duplicate_client_id_is_sanitized(
    db_client: TestClient, tracked_drafts: list[int],
) -> None:
    body = _body()
    first = db_client.post(PATH, json=body)
    assert first.status_code == 201
    tracked_drafts.append(first.json()["id"])
    again = db_client.post(PATH, json=body)
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "SERVICE_CLIENT_ID_EXISTS"


def test_admin_only_and_missing_resource(
    unauth_db_client: TestClient, tracked_drafts: list[int],
) -> None:
    headers = {
        "X-DQA-Dev-Actor": "nonadmin",
        "X-DQA-Dev-Roles": "query_operator",
    }
    assert unauth_db_client.get(PATH).status_code == 401
    assert unauth_db_client.get(PATH, headers=headers).status_code == 403
    assert unauth_db_client.post(PATH, headers=headers, json=_body()).status_code == 403

    # A client_id header is not a service authentication provider.
    assert unauth_db_client.get(PATH, headers={"X-Client-Id": "any-client"}).status_code == 401

    admin = {"X-DQA-Dev-Actor": "test-admin", "X-DQA-Dev-Roles": "administrator"}
    assert unauth_db_client.get(f"{PATH}/999999999", headers=admin).status_code == 404
    assert unauth_db_client.get(f"{PATH}/999999999/events", headers=admin).status_code == 404


def test_disabled_identity_provider_remains_fail_closed(
    unauth_client: TestClient, monkeypatch,
) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("DQA_AUTH_PROVIDER", "disabled")
    get_settings.cache_clear()
    try:
        response = unauth_client.get(
            PATH, headers={"X-DQA-Dev-Actor": "admin", "X-DQA-Dev-Roles": "administrator"}
        )
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "AUTH_PROVIDER_NOT_CONFIGURED"
    finally:
        get_settings.cache_clear()
