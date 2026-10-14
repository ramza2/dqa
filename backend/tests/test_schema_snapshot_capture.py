"""S-04-C-1 capture API and orchestration tests (synthetic; no Oracle/PG)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.config import Settings, get_settings
from app.services.schema_inspection import (
    CollectedSchemaSnapshot, SchemaInspectionError,
)
from app.services.schema_snapshot_history import CaptureResult, SnapshotHistoryError
from tests.test_schema_snapshot_history import FakeSession, _base, _capture

URL = "/api/v1/schema-inspector/snapshots/capture"


def _payload(expected=None, request_id=None):
    return {
        "capture_request_id": str(request_id or uuid4()),
        "expected_previous_revision_id": expected,
    }


def _stub_result():
    db = FakeSession()
    saved = _capture(db)
    saved.revision.captured_at = datetime.now(timezone.utc)
    return saved


def test_capture_requires_identity(unauth_client):
    response = unauth_client.post(URL, json=_payload())
    assert response.status_code == 401


@pytest.mark.parametrize("role", [
    "viewer", "auditor", "query_operator", "template_author", "template_approver",
])
def test_capture_requires_catalog_manage(unauth_client, role, monkeypatch):
    from app.api.routes import schema_inspector as api

    def forbidden(*_args, **_kwargs):
        raise AssertionError("non-admin must not call capture service")

    monkeypatch.setattr(api, "capture_configured_schema", forbidden)
    response = unauth_client.post(
        URL, json=_payload(),
        headers={"X-DQA-Dev-Actor": "non-admin", "X-DQA-Dev-Roles": role},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "AUTHORIZATION_DENIED"


def test_capture_disabled_default_fails_before_oracle_or_pg(client, monkeypatch):
    from app.services import schema_inspection as inspector

    def must_not_connect(*_args, **_kwargs):
        raise AssertionError("disabled Inspector must not open Oracle")

    monkeypatch.setenv("DQA_SCHEMA_INSPECTOR_ENABLED", "false")
    get_settings.cache_clear()
    monkeypatch.setattr(inspector, "create_engine", must_not_connect)
    response = client.post(URL, json=_payload())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "INSPECTOR_DISABLED"


def test_capture_forbids_client_target_sql_and_unknown_fields(client):
    for injection in (
        {"source_name": "somewhere_else"},
        {"schema_name": "SYS"},
        {"host": "attacker.example"},
        {"sql": "select * from patient"},
        {"database_name": "other"},
        {"credential_ref": "env:OTHER"},
    ):
        response = client.post(URL, json={**_payload(), **injection})
        assert response.status_code == 422


@pytest.mark.parametrize("payload", [
    {},
    {"capture_request_id": str(uuid4())},
    {"expected_previous_revision_id": None},
    {"capture_request_id": "bad", "expected_previous_revision_id": None},
    _payload(expected=-1),
])
def test_capture_requires_valid_uuid_and_explicit_cas(client, payload):
    response = client.post(URL, json=payload)
    assert response.status_code == 422


def test_capture_returns_sanitized_durable_summary(client, monkeypatch):
    from app.api.routes import schema_inspector as api

    saved = _stub_result()
    called = {}

    def stub(_settings, _session, **kwargs):
        called.update(kwargs)
        return saved

    monkeypatch.setattr(api, "capture_configured_schema", stub)
    req = _payload()
    response = client.post(URL, json=req)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "CAPTURED"
    assert body["created"] is True
    assert body["source_name"] == "oracle_demis_mock"
    assert body["id"] == saved.revision.id
    assert body["diff_status"] == "NO_BASELINE"
    assert body["total_changes"] is None
    assert body["imported"] is False
    assert body["activated"] is False
    assert "capture_request_id" not in response.text
    assert "snapshot_json" not in response.text
    assert "diff_summary_json" not in response.text
    assert called["captured_by"] == "test-admin"
    assert str(called["capture_request_id"]) == req["capture_request_id"]
    assert called["expected_previous_revision_id"] is None


@pytest.mark.parametrize("code,expected_http", [
    ("INSPECTOR_DISABLED", 503),
    ("INSPECTOR_ENV_NOT_ALLOWED", 503),
    ("INSPECTOR_NOT_CONFIGURED", 503),
    ("INSPECTOR_METADATA_FAILED", 502),
    ("STALE_SNAPSHOT_REVISION", 409),
    ("CAPTURE_REQUEST_REUSED", 409),
    ("TARGET_IDENTITY_MISMATCH", 409),
    ("CORRUPT_BASELINE", 409),
    ("INVALID_SNAPSHOT", 422),
    ("DIFF_TOO_LARGE", 413),
])
def test_capture_public_error_contract(client, monkeypatch, code, expected_http):
    from app.api.routes import schema_inspector as api

    def failing(*_args, **_kwargs):
        exc_type = SchemaInspectionError if code.startswith("INSPECTOR_") else SnapshotHistoryError
        raise exc_type(code)

    monkeypatch.setattr(api, "capture_configured_schema", failing)
    response = client.post(URL, json=_payload())
    assert response.status_code == expected_http
    assert response.json()["detail"]["code"] == code
    assert "traceback" not in response.text.lower()


def test_capture_unexpected_exception_never_exposes_secret(client, monkeypatch):
    from app.api.routes import schema_inspector as api

    def failing(*_args, **_kwargs):
        raise RuntimeError("sensitive-oracle-host sensitive-credential")

    monkeypatch.setattr(api, "capture_configured_schema", failing)
    response = client.post(URL, json=_payload())
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "SNAPSHOT_CAPTURE_FAILED"
    assert "sensitive-oracle-host" not in response.text
    assert "sensitive-credential" not in response.text


def test_orchestration_captures_configured_source_and_commits(monkeypatch):
    from app.services import schema_snapshot_capture as service

    collected = CollectedSchemaSnapshot("oracle_demis_mock", _base())
    monkeypatch.setattr(service, "collect_configured_schema_snapshot", lambda _: collected)
    class CommittingFakeSession(FakeSession):
        commits = 0
        rollbacks = 0
        def commit(self):
            self.commits += 1
        def rollback(self):
            self.rollbacks += 1

    db = CommittingFakeSession()
    req = uuid4()
    saved = service.capture_configured_schema(
        Settings(_env_file=None), db, captured_by="test-admin",
        capture_request_id=req, expected_previous_revision_id=None,
    )
    assert saved.created
    assert saved.revision.source_name == "oracle_demis_mock"
    assert saved.revision.captured_by == "test-admin"
    assert saved.revision.capture_request_id == str(req)
    assert db.commits == 1 and db.rollbacks == 0


def test_orchestration_rolls_back_on_stale_guard(monkeypatch):
    from app.services import schema_snapshot_capture as service

    collected = CollectedSchemaSnapshot("oracle_demis_mock", _base())
    monkeypatch.setattr(service, "collect_configured_schema_snapshot", lambda _: collected)
    class RollbackFakeSession(FakeSession):
        commits = 0
        rollbacks = 0
        def commit(self):
            self.commits += 1
        def rollback(self):
            self.rollbacks += 1

    db = RollbackFakeSession()
    _capture(db)
    with pytest.raises(SnapshotHistoryError, match="STALE_SNAPSHOT_REVISION"):
        service.capture_configured_schema(
            Settings(_env_file=None), db, captured_by="test-admin",
            capture_request_id=uuid4(), expected_previous_revision_id=None,
        )
    assert db.commits == 0 and db.rollbacks == 1
