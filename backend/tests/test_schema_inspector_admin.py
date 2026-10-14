"""S-01/S-02 admin-only, fail-closed schema-inspection HTTP/service tests.

All successful runs use a synthetic Engine and Snapshot; never connect to Oracle.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine as sqlalchemy_create_engine

from app.adapters.schema_inspector.base import InspectedTable, SchemaSnapshot
from app.core.config import Settings, get_settings
from app.services.schema_inspection import (
    SchemaInspectionError,
    _target_from_settings,
)

URL = "/api/v1/schema-inspector/inspect"


def _configure(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "APP_ENV": "test",
        "DQA_SCHEMA_INSPECTOR_ENABLED": "true",
        "DQA_SCHEMA_INSPECTOR_SOURCE_NAME": "oracle_demis_mock",
        "DQA_SCHEMA_INSPECTOR_SCHEMA_NAME": "DEMIS_OWNER",
        "DQA_SCHEMA_INSPECTOR_HOST": "fake-inspector-host",
        "DQA_SCHEMA_INSPECTOR_PORT": "1521",
        "DQA_SCHEMA_INSPECTOR_SERVICE_NAME": "FREEPDB1",
        "DQA_SCHEMA_INSPECTOR_USERNAME": "metadata_reader",
        "DQA_SCHEMA_INSPECTOR_CREDENTIAL_REF": "env:DEMIS_INSPECT_SECRET_TEST",
        "DEMIS_INSPECT_SECRET_TEST": "synthetic-only-pass",
    }
    for key, val in values.items():
        monkeypatch.setenv(key, val)
    get_settings.cache_clear()


def test_inspection_disabled_by_default(client, monkeypatch):
    monkeypatch.setenv("DQA_SCHEMA_INSPECTOR_ENABLED", "false")
    get_settings.cache_clear()
    response = client.post(URL, json={})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "INSPECTOR_DISABLED"


@pytest.mark.parametrize("role", [
    "viewer", "auditor", "query_operator", "template_author", "template_approver",
])
def test_non_administrator_cannot_inspect(unauth_client, monkeypatch, role):
    _configure(monkeypatch)
    response = unauth_client.post(
        URL, json={},
        headers={"X-DQA-Dev-Actor": "role-check", "X-DQA-Dev-Roles": role},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "AUTHORIZATION_DENIED"


def test_missing_identity_cannot_inspect(unauth_client, monkeypatch):
    _configure(monkeypatch)
    response = unauth_client.post(URL, json={})
    assert response.status_code == 401


def test_request_cannot_override_schema_or_connection(client, monkeypatch):
    _configure(monkeypatch)
    response = client.post(URL, json={
        "schema_name": "SYS", "host": "attacker.example", "sql": "SELECT * FROM patients"
    })
    assert response.status_code == 422


def test_explicit_inspect_returns_counts_without_metadata_or_secret(client, monkeypatch):
    _configure(monkeypatch)
    observed = {}

    def fake_engine_factory(url, **kwargs):
        observed["url"] = url
        observed["kwargs"] = kwargs
        return sqlalchemy_create_engine("sqlite+pysqlite:///:memory:")

    class StubInspector:
        def __init__(self, engine, database_name):
            assert database_name == "FREEPDB1"

        def inspect(self, schema_name):
            observed["schema_name"] = schema_name
            return SchemaSnapshot(
                db_type="oracle", database_name="FREEPDB1",
                schema_name=schema_name,
                tables=[
                    InspectedTable(schema_name=schema_name, table_name="TB_FAKE",
                                   table_type="BASE TABLE", table_comment="synthetic"),
                ],
            )

    monkeypatch.setattr(
        "app.services.schema_inspection.create_engine", fake_engine_factory
    )
    monkeypatch.setattr(
        "app.services.schema_inspection.OracleSchemaInspector", StubInspector
    )
    response = client.post(URL, json={})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "INSPECTED"
    assert data["source_name"] == "oracle_demis_mock"
    assert data["schema_name"] == "DEMIS_OWNER"
    assert data["table_count"] == 1
    assert data["column_count"] == 0
    assert data["imported"] is False
    assert data["activated"] is False
    assert "TB_FAKE" not in response.text
    assert "synthetic-only-pass" not in response.text
    assert "fake-inspector-host" not in response.text
    assert observed["schema_name"] == "DEMIS_OWNER"
    assert observed["url"].username == "metadata_reader"
    assert observed["url"].host == "fake-inspector-host"
    assert observed["url"].password == "synthetic-only-pass"
    assert observed["kwargs"]["connect_args"]["tcp_connect_timeout"] == 5


@pytest.mark.parametrize("override", [
    {"DQA_SCHEMA_INSPECTOR_SCHEMA_NAME": "SYS"},
    {"DQA_SCHEMA_INSPECTOR_SCHEMA_NAME": " DEMIS_OWNER"},
    {"DQA_SCHEMA_INSPECTOR_HOST": "user:pass@host"},
    {"DQA_SCHEMA_INSPECTOR_CREDENTIAL_REF": "env:DEMIS_SECRET_ORACLE_PASSWORD"},
    {"DQA_SCHEMA_INSPECTOR_CREDENTIAL_REF": "plain_password"},
    {"DQA_SCHEMA_INSPECTOR_ENABLED": "false"},
])
def test_invalid_config_fails_before_connection(client, monkeypatch, override):
    _configure(monkeypatch)
    for key, val in override.items():
        monkeypatch.setenv(key, val)
    get_settings.cache_clear()

    def must_not_connect(*args, **kwargs):
        raise AssertionError("no Oracle/engine connection allowed")

    monkeypatch.setattr(
        "app.services.schema_inspection.create_engine", must_not_connect
    )
    response = client.post(URL, json={})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] in {
        "INSPECTOR_DISABLED", "INSPECTOR_NOT_CONFIGURED"
    }


def test_missing_inspector_secret_fails_before_engine(client, monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv(
        "DQA_SCHEMA_INSPECTOR_CREDENTIAL_REF", "env:DEMIS_INSPECT_SECRET_ABSENT"
    )
    monkeypatch.delenv("DEMIS_INSPECT_SECRET_ABSENT", raising=False)
    get_settings.cache_clear()

    def must_not_connect(*args, **kwargs):
        raise AssertionError("secret was unavailable; no connection permitted")

    monkeypatch.setattr(
        "app.services.schema_inspection.create_engine", must_not_connect
    )
    response = client.post(URL, json={})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "INSPECTOR_NOT_CONFIGURED"


def test_driver_error_does_not_expose_credentials(client, monkeypatch):
    _configure(monkeypatch)

    def fake_engine_factory(*args, **kwargs):
        return sqlalchemy_create_engine("sqlite+pysqlite:///:memory:")

    class FailingInspector:
        def __init__(self, *_args):
            pass

        def inspect(self, schema_name):
            raise RuntimeError(
                "sensitive detail: synthetic-only-pass fake-inspector-host"
            )

    monkeypatch.setattr(
        "app.services.schema_inspection.create_engine", fake_engine_factory
    )
    monkeypatch.setattr(
        "app.services.schema_inspection.OracleSchemaInspector", FailingInspector
    )
    response = client.post(URL, json={})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "INSPECTOR_METADATA_FAILED"
    assert "synthetic-only-pass" not in response.text
    assert "fake-inspector-host" not in response.text


def test_production_inspection_blocked_even_if_enabled():
    settings = Settings(
        _env_file=None,
        APP_ENV="production",
        DQA_SCHEMA_INSPECTOR_ENABLED=True,
    )
    with pytest.raises(SchemaInspectionError) as ex:
        _target_from_settings(settings)
    assert ex.value.code == "INSPECTOR_ENV_NOT_ALLOWED"
