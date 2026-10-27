"""Mock-only Inspector binding contracts. No real DB, mock Oracle or PG I/O."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
import pytest

from app.core.config import Settings
from app.services import mock_inspector_binding as binding
from app.services import oracle_mock_actions as mock
from app.adapters.db.deps import get_db_session
from app.core.config import get_settings


def settings(**extra):
    values = {
        "APP_ENV": "development",
        "DQA_AUTH_PROVIDER": "dev_headers",
        "DQA_DEV_ORACLE_MOCK_ACTIONS_ENABLED": True,
        "DQA_SCHEMA_INSPECTOR_ENABLED": True,
        "DQA_SCHEMA_INSPECTOR_SOURCE_NAME": mock.MOCK_SOURCE,
        "DQA_SCHEMA_INSPECTOR_SCHEMA_NAME": "DEMIS_OWNER",
        "DQA_SCHEMA_INSPECTOR_HOST": mock.MOCK_HOST,
        "DQA_SCHEMA_INSPECTOR_PORT": mock.MOCK_PORT,
        "DQA_SCHEMA_INSPECTOR_SERVICE_NAME": mock.MOCK_SERVICE,
        "DQA_SCHEMA_INSPECTOR_USERNAME": "DEMIS_INSPECT_RO",
        "DQA_SCHEMA_INSPECTOR_CREDENTIAL_REF": "env:DEMIS_INSPECT_SECRET_MOCK",
    }
    values.update(extra)
    return Settings(_env_file=None, **values)


def profile(**extra):
    values = dict(
        id=71, name="Mock", source_name=mock.MOCK_SOURCE, enabled=True,
        environment=mock.MOCK_ENVIRONMENT, dbms_type=mock.MOCK_DBMS,
        host=mock.MOCK_HOST, port=mock.MOCK_PORT, database_name=mock.MOCK_SERVICE,
        username=mock.MOCK_USERNAME, credential_secret_ref=mock.MOCK_CREDENTIAL_REF,
    )
    values.update(extra)
    return SimpleNamespace(**values)


def mock_get(monkeypatch, p):
    monkeypatch.setattr(binding, "get_connection_profile", lambda _s, _id: p)


def test_selected_mock_ready_without_connecting(monkeypatch):
    mock_get(monkeypatch, profile())
    assert binding.require_mock_inspector_binding(object(), 71, settings()).id == 71


@pytest.mark.parametrize("diff,code", [
    ({"enabled": False}, "MOCK_PROFILE_INACTIVE"),
    ({"host": "production.invalid"}, "MOCK_PROFILE_MISMATCH"),
    ({"source_name": "demis_live"}, "MOCK_PROFILE_MISMATCH"),
    ({"credential_secret_ref": "env:WRONG"}, "MOCK_PROFILE_MISMATCH"),
])
def test_profile_mismatch_denied(monkeypatch, diff, code):
    mock_get(monkeypatch, profile(**diff))
    with pytest.raises(binding.MockInspectorBindingError) as exc:
        binding.require_mock_inspector_binding(object(), 71, settings())
    assert exc.value.code == code


@pytest.mark.parametrize("setting,code", [
    ({"DQA_SCHEMA_INSPECTOR_ENABLED": False}, "INSPECTOR_DISABLED"),
    ({"DQA_SCHEMA_INSPECTOR_HOST": "other.invalid"}, "MOCK_INSPECTOR_TARGET_MISMATCH"),
    ({"DQA_SCHEMA_INSPECTOR_SOURCE_NAME": "other"}, "MOCK_INSPECTOR_TARGET_MISMATCH"),
    ({"DQA_SCHEMA_INSPECTOR_SERVICE_NAME": "WRONG"}, "MOCK_INSPECTOR_TARGET_MISMATCH"),
    ({"DQA_SCHEMA_INSPECTOR_USERNAME": mock.MOCK_USERNAME}, "MOCK_INSPECTOR_ACCOUNT_NOT_SEPARATE"),
    ({"DQA_SCHEMA_INSPECTOR_CREDENTIAL_REF": "env:DEMIS_SECRET_ORACLE_PASSWORD"}, "INSPECTOR_NOT_CONFIGURED"),
    ({"APP_ENV": "production"}, "MOCK_INSPECTOR_DISABLED"),
    ({"DQA_DEV_ORACLE_MOCK_ACTIONS_ENABLED": False}, "MOCK_INSPECTOR_DISABLED"),
])
def test_server_config_denied_before_connection(monkeypatch, setting, code):
    mock_get(monkeypatch, profile())
    with pytest.raises(binding.MockInspectorBindingError) as exc:
        binding.require_mock_inspector_binding(object(), 71, settings(**setting))
    assert exc.value.code == code


def test_http_mock_readiness_inspect_capture_safety(client, monkeypatch):
    from app.api.routes import schema_inspector as routes
    def no_db():
        yield object()
    client.app.dependency_overrides[get_db_session] = no_db
    client.app.dependency_overrides[get_settings] = lambda: settings()
    mock_get(monkeypatch, profile())
    summary = {
        "source_name": mock.MOCK_SOURCE, "schema_name": "DEMIS_OWNER",
        "table_count": 2, "column_count": 8,
        "primary_key_column_count": 2, "unique_key_column_count": 0,
        "foreign_key_count": 1, "index_count": 1,
        "imported": False, "activated": False,
    }
    monkeypatch.setattr(routes, "inspect_configured_schema", lambda _s: summary)
    from tests.test_schema_snapshot_capture import _stub_result
    captured = _stub_result()
    monkeypatch.setattr(routes, "capture_configured_schema", lambda *_a, **_kw: captured)
    try:
        base = "/api/v1/schema-inspector/mock-targets/71"
        ready = client.get(base + "/readiness")
        assert ready.status_code == 200
        assert ready.json()["ready"] is True
        assert ready.json()["site_approved"] is False
        assert ready.json()["catalog_activated"] is False

        scan = client.post(base + "/inspect", json={})
        assert scan.status_code == 200
        assert scan.json()["table_count"] == 2
        assert scan.json()["activated"] is False

        rejected = client.post(base + "/inspect", json={"host": "another"})
        assert rejected.status_code == 422

        captured_result = client.post(base + "/snapshots/capture", json={
            "capture_request_id": str(uuid4()),
            "expected_previous_revision_id": None,
        })
        assert captured_result.status_code == 200, captured_result.text
        assert captured_result.json()["activated"] is False
        assert captured_result.json()["imported"] is False
        assert captured_result.json()["created"] is True
        assert "snapshot_json" not in captured_result.text
    finally:
        client.app.dependency_overrides.clear()


def test_http_denies_non_admin_before_db_or_oracle(unauth_client, monkeypatch):
    from app.api.routes import schema_inspector as routes
    monkeypatch.setattr(routes, "require_mock_inspector_binding",
                        lambda *_args: pytest.fail("unauthorized must not bind"))
    base = "/api/v1/schema-inspector/mock-targets/71"
    for url,method,json_body in [
        (base + "/readiness", "get", None),
        (base + "/inspect", "post", {}),
        (base + "/snapshots/capture", "post", {
            "capture_request_id": str(uuid4()), "expected_previous_revision_id": None
        }),
    ]:
        resp = getattr(unauth_client,method)(url, **({"json":json_body} if json_body is not None else {}),
            headers={"X-DQA-Dev-Actor": "viewer", "X-DQA-Dev-Roles": "viewer"})
        assert resp.status_code == 403


def test_http_mismatch_prevents_oracle(client, monkeypatch):
    from app.api.routes import schema_inspector as routes
    def no_db():
        yield object()
    client.app.dependency_overrides[get_db_session] = no_db
    client.app.dependency_overrides[get_settings] = lambda: settings(
        DQA_SCHEMA_INSPECTOR_HOST="not-pinned.invalid"
    )
    mock_get(monkeypatch, profile())
    monkeypatch.setattr(routes, "inspect_configured_schema",
        lambda *_a: pytest.fail("no Oracle on mismatch"))
    monkeypatch.setattr(routes, "capture_configured_schema",
        lambda *_a, **_kw: pytest.fail("no Oracle on mismatch"))
    base = "/api/v1/schema-inspector/mock-targets/71"
    try:
        r=client.get(base + "/readiness")
        assert r.status_code == 200
        assert r.json()["ready"] is False
        assert r.json()["reason_code"] == "MOCK_INSPECTOR_TARGET_MISMATCH"
        assert client.post(base + "/inspect",json={}).status_code == 409
        assert client.post(base + "/snapshots/capture",json={
            "capture_request_id":str(uuid4()),"expected_previous_revision_id":None,
        }).status_code == 409
    finally:
        client.app.dependency_overrides.clear()
