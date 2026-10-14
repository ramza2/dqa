"""Admin change-review HTTP contract; synthetic no-DB no-Oracle tests."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.services.schema_snapshot_review_events import ReviewEventResult

URL = "/api/v1/schema-inspector/snapshots/1/reviews"
FP = "a" * 64


def _body(**changes):
    data = {
        "review_request_id": str(uuid4()),
        "expected_schema_fingerprint": FP,
        "expected_previous_review_event_id": None,
        "decision": "ACKNOWLEDGED",
        "reason_code": "REVIEWED_CHANGES",
    }
    data.update(changes)
    return data


def test_no_identity(unauth_client):
    response = unauth_client.post(URL + "?source_name=oracle_demis_mock", json=_body())
    assert response.status_code == 401


@pytest.mark.parametrize("role", [
    "viewer", "auditor", "query_operator", "template_author", "template_approver",
])
def test_nonadmin_cannot_post(unauth_client, role):
    response = unauth_client.post(
        URL + "?source_name=oracle_demis_mock", json=_body(),
        headers={"X-DQA-Dev-Actor": "not-admin", "X-DQA-Dev-Roles": role},
    )
    assert response.status_code == 403


def test_default_disabled_no_service_execution(client, monkeypatch):
    from app.api.routes import schema_snapshot_history as api

    monkeypatch.setenv("DQA_SCHEMA_SNAPSHOT_REVIEW_ENABLED", "false")
    get_settings.cache_clear()

    def forbidden(*args, **kwargs):
        raise AssertionError("disabled review must not write")

    monkeypatch.setattr(api, "record_review_event", forbidden)
    response = client.post(URL + "?source_name=oracle_demis_mock", json=_body())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "SNAPSHOT_REVIEW_WRITES_DISABLED"


def test_production_guard_even_when_enabled(client, monkeypatch):
    from app.api.routes import schema_snapshot_history as api
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DQA_SCHEMA_SNAPSHOT_REVIEW_ENABLED", "true")
    get_settings.cache_clear()

    def forbidden(*args, **kwargs):
        raise AssertionError("production review unavailable")

    monkeypatch.setattr(api, "record_review_event", forbidden)
    response = client.post(URL + "?source_name=oracle_demis_mock", json=_body())
    assert response.status_code in (401, 503)


@pytest.mark.parametrize("invalid", [
    {"review_request_id": "invalid"},
    {"expected_schema_fingerprint": "bad"},
    {"expected_previous_review_event_id": -1},
    {"decision": "APPROVED"},
    {"reason_code": "SENSITIVE COMMENT"},
    {"reviewed_by": "forged"},
    {"independent_preflight_verified": True},
    {"catalog_ready": True},
    {"sql": "SELECT * FROM TB_PATIENT"},
])
def test_invalid_body_rejected_without_write(client, monkeypatch, invalid):
    from app.api.routes import schema_snapshot_history as api
    monkeypatch.setenv("DQA_SCHEMA_SNAPSHOT_REVIEW_ENABLED", "true")
    get_settings.cache_clear()

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid request must not write")

    monkeypatch.setattr(api, "record_review_event", forbidden)
    response = client.post(
        URL + "?source_name=oracle_demis_mock",
        json=_body(**invalid),
    )
    assert response.status_code == 422


def test_admin_record_response_never_claims_ready(client, monkeypatch):
    from app.api.routes import schema_snapshot_history as api
    monkeypatch.setenv("DQA_SCHEMA_SNAPSHOT_REVIEW_ENABLED", "true")
    get_settings.cache_clear()

    calls = {}
    row = SimpleNamespace(
        id=1, source_name="oracle_demis_mock", snapshot_revision_id=1,
        schema_fingerprint=FP, previous_review_event_id=None,
        decision="ACKNOWLEDGED", reason_code="REVIEWED_CHANGES",
        reviewed_by="test-admin", reviewed_at=datetime.now(timezone.utc),
    )

    def stub(_session, **kwargs):
        calls.update(kwargs)
        return ReviewEventResult(row, created=True)

    monkeypatch.setattr(api, "record_review_event", stub)
    req = _body()
    response = client.post(URL + "?source_name=oracle_demis_mock", json=req)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["created"] is True
    assert data["catalog_ready"] is False
    assert data["catalog_activated"] is False
    assert data["independent_preflight_verified"] is False
    assert "review_request_id" not in response.text
    assert calls["reviewed_by"] == "test-admin"
    assert str(calls["review_request_id"]) == req["review_request_id"]


def test_errors_sanitized(client, monkeypatch):
    from app.api.routes import schema_snapshot_history as api
    from app.services.schema_snapshot_review_events import SnapshotReviewEventError

    monkeypatch.setenv("DQA_SCHEMA_SNAPSHOT_REVIEW_ENABLED", "true")
    get_settings.cache_clear()

    for code, status in (
        ("SNAPSHOT_REVISION_NOT_FOUND", 404),
        ("STALE_SNAPSHOT_REVISION", 409),
        ("STALE_SNAPSHOT_FINGERPRINT", 409),
        ("STALE_REVIEW_EVENT", 409),
        ("REVIEW_REQUEST_REUSED", 409),
        ("SNAPSHOT_REVIEW_UNVERIFIABLE", 409),
    ):
        def stub(*args, **kwargs):
            raise SnapshotReviewEventError(code)

        monkeypatch.setattr(api, "record_review_event", stub)
        response = client.post(URL + "?source_name=oracle_demis_mock", json=_body())
        assert response.status_code == status
        assert response.json()["detail"]["code"] == code
        assert FP not in response.text

    def secret_error(*args, **kwargs):
        raise RuntimeError("hidden-db-password")

    monkeypatch.setattr(api, "record_review_event", secret_error)
    response = client.post(URL + "?source_name=oracle_demis_mock", json=_body())
    assert response.status_code == 500
    assert "hidden-db-password" not in response.text
