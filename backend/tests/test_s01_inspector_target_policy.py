"""S-01 Inspector operator-config policy: synthetic-only and fail-closed.

No network, database, Oracle, credentials, real DEMIS or clinical data.
These tests guard *configuration*, not military DBA authorization of a host,
schema or account privileges.
"""
from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.services.schema_inspection import _target_from_settings
from tests.test_schema_inspector_admin import _configure

URL = "/api/v1/schema-inspector/inspect"


@pytest.mark.parametrize("override", [
    {"DQA_SCHEMA_INSPECTOR_HOST": "user:password@host"},
    {"DQA_SCHEMA_INSPECTOR_HOST": "https://db.example"},
    {"DQA_SCHEMA_INSPECTOR_HOST": "db-host/internal"},
    {"DQA_SCHEMA_INSPECTOR_HOST": "db..invalid"},
    {"DQA_SCHEMA_INSPECTOR_HOST": "-invalid.example"},
    {"DQA_SCHEMA_INSPECTOR_HOST": "x" * 254},
    {"DQA_SCHEMA_INSPECTOR_HOST": "db.example\nX-Leak: secret"},
    {"DQA_SCHEMA_INSPECTOR_HOST": "db_unsafe"},
    {"DQA_SCHEMA_INSPECTOR_SERVICE_NAME": "ORCLPDB1;DROP"},
    {"DQA_SCHEMA_INSPECTOR_SERVICE_NAME": "PDB/SECRET"},
    {"DQA_SCHEMA_INSPECTOR_SERVICE_NAME": "PDB example"},
    {"DQA_SCHEMA_INSPECTOR_SERVICE_NAME": "PDB\nwrong"},
    {"DQA_SCHEMA_INSPECTOR_USERNAME": "SYS"},
    {"DQA_SCHEMA_INSPECTOR_USERNAME": "SYSTEM"},
    {"DQA_SCHEMA_INSPECTOR_USERNAME": "user/password"},
    {"DQA_SCHEMA_INSPECTOR_USERNAME": "user name"},
    {"DQA_SCHEMA_INSPECTOR_CREDENTIAL_REF": "env:DEMIS_INSPECT_SECRET_"},
    {"DQA_SCHEMA_INSPECTOR_CREDENTIAL_REF": "env:DEMIS_INSPECT_SECRET_TEST\nLEAK"},
    {"DQA_SCHEMA_INSPECTOR_CREDENTIAL_REF": "env:DEMIS_INSPECT_SECRET_TEST.other"},
    {"DQA_SCHEMA_INSPECTOR_CREDENTIAL_REF": "env:DEMIS_INSPECT_SECRET_TEST:other"},
    {"DQA_DEMIS_CREDENTIAL_ENV_PREFIX": "DEMIS_"},
    {"DQA_DEMIS_CREDENTIAL_ENV_PREFIX": "DEMIS_INSPECT_"},
    {"DQA_DEMIS_CREDENTIAL_ENV_PREFIX": "DEMIS_INSPECT_SECRET_"},
    {"DQA_DEMIS_CREDENTIAL_ENV_PREFIX": "DEMIS_INSPECT_SECRET_OTHER_"},
    {"DQA_DEMIS_CREDENTIAL_ENV_PREFIX": "wrong-prefix;"},
])
def test_invalid_operator_target_or_credential_namespace_blocks_before_lookup(
    client, monkeypatch, override
):
    _configure(monkeypatch)
    for key, val in override.items():
        monkeypatch.setenv(key, val)
    get_settings.cache_clear()

    from app.services import schema_inspection as service

    def forbidden(*_args, **_kwargs):
        pytest.fail("invalid Inspector config must not touch secrets or network")

    monkeypatch.setattr(service, "EnvironmentCredentialResolver", forbidden)
    monkeypatch.setattr(service, "create_engine", forbidden)

    response = client.post(URL, json={})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "INSPECTOR_NOT_CONFIGURED"
    for marker in ("password@", "X-Leak", "secret", "DEMIS_INSPECT_SECRET"):
        assert marker not in response.text


@pytest.mark.parametrize("host,service,username", [
    ("fake-inspector-host", "FREEPDB1", "metadata_reader"),
    ("schema-db.example.internal", "orclpdb1.example.internal", "SCHEMA_READER"),
    ("127.0.0.1", "PDB_1", "C##METADATA"),
    ("::1", "PDB_1", "INSPECT$USER"),
])
def test_valid_synthetic_operator_config_only_builds_target(
    monkeypatch, host, service, username
):
    _configure(monkeypatch)
    monkeypatch.setenv("DQA_SCHEMA_INSPECTOR_HOST", host)
    monkeypatch.setenv("DQA_SCHEMA_INSPECTOR_SERVICE_NAME", service)
    monkeypatch.setenv("DQA_SCHEMA_INSPECTOR_USERNAME", username)
    get_settings.cache_clear()
    result = _target_from_settings(get_settings())
    assert result.host == host
    assert result.service_name == service
    assert result.username == username
    assert result.credential_ref == "env:DEMIS_INSPECT_SECRET_TEST"


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_site_environment_block_precedes_target_and_credentials(
    monkeypatch, environment
):
    _configure(monkeypatch)
    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setenv("DQA_SCHEMA_INSPECTOR_HOST", "not valid host")
    get_settings.cache_clear()
    from app.services.schema_inspection import SchemaInspectionError

    with pytest.raises(SchemaInspectionError) as err:
        _target_from_settings(get_settings())
    assert err.value.code == "INSPECTOR_ENV_NOT_ALLOWED"


def test_disabled_inspector_blocks_even_with_invalid_operator_config(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("DQA_SCHEMA_INSPECTOR_ENABLED", "false")
    monkeypatch.setenv("DQA_DEMIS_CREDENTIAL_ENV_PREFIX", "DEMIS_INSPECT_SECRET_")
    get_settings.cache_clear()
    from app.services.schema_inspection import SchemaInspectionError

    with pytest.raises(SchemaInspectionError) as err:
        _target_from_settings(get_settings())
    assert err.value.code == "INSPECTOR_DISABLED"
