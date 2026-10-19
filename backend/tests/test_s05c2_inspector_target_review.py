"""S-05-C2 synthetic-only no-I/O Inspector/Profile metadata review.

Never use db_session/db_client: root fixtures TRUNCATE live DQA tables.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.adapters.connection_profile.errors import ConnectionProfileError, ConnectionProfileErrorCode
from app.adapters.db.deps import get_db_session
from app.core.config import Settings
from app.schemas.connection_profile import ConnectionProfileView
from app.services.inspector_target_review import review_inspector_target_configuration


def _profile(**overrides) -> ConnectionProfileView:
    data = {
        "id": 5, "name": "Synthetic replica", "source_name": "fake_source",
        "environment": "test", "enabled": False, "dbms_type": "oracle",
        "host": "synthetic.invalid", "port": 1521,
        "database_name": "SYNTHETICPDB", "username": "metadata_reader",
        "credential_secret_ref": "env:DEMIS_SECRET_SYNTHETIC",
        "created_at": datetime(2026, 10, 16, tzinfo=UTC),
        "updated_at": datetime(2026, 10, 16, tzinfo=UTC),
    }
    data.update(overrides)
    return ConnectionProfileView(**data)


def _settings(**overrides) -> Settings:
    data = {
        "APP_ENV": "test",
        "DQA_SCHEMA_INSPECTOR_ENABLED": True,
        "DQA_SCHEMA_INSPECTOR_SOURCE_NAME": "fake_source",
        "DQA_SCHEMA_INSPECTOR_SCHEMA_NAME": "FAKE_SCHEMA",
        "DQA_SCHEMA_INSPECTOR_HOST": "synthetic.invalid",
        "DQA_SCHEMA_INSPECTOR_PORT": 1521,
        "DQA_SCHEMA_INSPECTOR_SERVICE_NAME": "SYNTHETICPDB",
        "DQA_SCHEMA_INSPECTOR_USERNAME": "metadata_reader",
        "DQA_SCHEMA_INSPECTOR_CREDENTIAL_REF": "env:DEMIS_INSPECT_SECRET_SYNTHETIC",
        "DQA_DEMIS_CREDENTIAL_ENV_PREFIX": "DEMIS_SECRET_",
    }
    data.update(overrides)
    return Settings(_env_file=None, **data)


def _never_authorized(result) -> None:
    assert result.connection_authorized is False
    assert result.inspector_bound_to_profile is False
    assert result.credential_values_resolved is False
    assert result.live_connection_tested is False
    serialized = result.model_dump_json()
    for raw in ("synthetic.invalid", "metadata_reader", "SYNTHETICPDB",
                "DEMIS_INSPECT_SECRET_", "DEMIS_SECRET_SYNTHETIC"):
        assert raw not in serialized


def test_review_valid_synthetic_match_still_not_authorized(monkeypatch):
    from app.services import schema_inspection
    monkeypatch.setattr(schema_inspection, "create_engine",
                        lambda *_a, **_k: pytest.fail("NO ENGINE"))
    monkeypatch.setattr(schema_inspection, "EnvironmentCredentialResolver",
                        lambda *_a, **_k: pytest.fail("NO CREDENTIAL"))
    result = review_inspector_target_configuration(_profile(), _settings())
    assert result.inspector_configuration_state == "CONFIGURED_UNVERIFIED"
    assert result.comparison_state == "STRUCTURAL_MATCH_UNVERIFIED"
    assert result.mismatch_fields == []
    _never_authorized(result)


@pytest.mark.parametrize("changes,fields", [
    ({"source_name": "wrong_source"}, ["source_name"]),
    ({"host": "other.invalid", "port": 5444}, ["host", "port"]),
    ({"database_name": "WRONG_SERVICE", "username": "other_reader"},
     ["database_name_vs_service_name", "username"]),
    ({"dbms_type": "postgresql", "environment": "development"},
     ["environment", "dbms_type"]),
])
def test_review_mismatch_never_approves(changes, fields):
    result = review_inspector_target_configuration(_profile(**changes), _settings())
    assert result.comparison_state == "TARGET_METADATA_MISMATCH"
    assert result.mismatch_fields == fields
    _never_authorized(result)


@pytest.mark.parametrize("settings_overrides,state", [
    ({"DQA_SCHEMA_INSPECTOR_ENABLED": False}, "DISABLED"),
    ({"APP_ENV": "production"}, "ENV_BLOCKED"),
    ({"APP_ENV": "staging"}, "ENV_BLOCKED"),
    ({"DQA_SCHEMA_INSPECTOR_HOST": "user:pass@invalid"}, "INVALID"),
    ({"DQA_SCHEMA_INSPECTOR_CREDENTIAL_REF": "env:DEMIS_SECRET_SYNTHETIC"}, "INVALID"),
    ({"DQA_SCHEMA_INSPECTOR_USERNAME": None}, "INVALID"),
])
def test_review_fail_closed_config_states(settings_overrides, state):
    result = review_inspector_target_configuration(
        _profile(), _settings(**settings_overrides)
    )
    assert result.inspector_configuration_state == state
    assert result.comparison_state == "NOT_COMPARABLE"
    assert result.mismatch_fields == []
    _never_authorized(result)


def test_http_requires_profile_manage_and_never_reaches_db_or_inspector(client, monkeypatch):
    from app.api.routes import connection_profiles as route
    from app.services import schema_inspection
    calls = {"profile": 0}

    def forbidden(*_args, **_kwargs):
        pytest.fail("review must not resolve credentials or open an Oracle engine")

    monkeypatch.setattr(schema_inspection, "create_engine", forbidden)
    monkeypatch.setattr(schema_inspection, "EnvironmentCredentialResolver", forbidden)

    def no_real_db():
        yield object()  # never used; route's profile get is mocked

    def profile_stub(_session, _id):
        calls["profile"] += 1
        assert _id == 5
        return _profile()

    client.app.dependency_overrides[get_db_session] = no_real_db
    monkeypatch.setattr(route, "get_connection_profile", profile_stub)
    from app.core.config import get_settings
    client.app.dependency_overrides[get_settings] = lambda: _settings()
    try:
        denied = client.get(
            "/api/v1/connection-profiles/5/inspector-target-review",
            headers={"X-DQA-Dev-Actor": "synthetic-viewer", "X-DQA-Dev-Roles": "viewer"},
        )
        assert denied.status_code == 403
        assert calls["profile"] == 0  # RBAC denies before profile lookup
        ok = client.get("/api/v1/connection-profiles/5/inspector-target-review")
        assert ok.status_code == 200, ok.text
        assert calls["profile"] == 1
        assert ok.json()["comparison_state"] == "STRUCTURAL_MATCH_UNVERIFIED"
        assert ok.json()["connection_authorized"] is False
        for secret in ("synthetic.invalid", "DEMIS_INSPECT_SECRET_", "metadata_reader"):
            assert secret not in ok.text
    finally:
        client.app.dependency_overrides.clear()


def test_http_missing_profile_sanitized_404(client, monkeypatch):
    from app.api.routes import connection_profiles as route

    def no_real_db():
        yield object()

    def missing(_session, _id):
        raise ConnectionProfileError(ConnectionProfileErrorCode.NOT_FOUND, "no such profile")

    client.app.dependency_overrides[get_db_session] = no_real_db
    monkeypatch.setattr(route, "get_connection_profile", missing)
    try:
        response = client.get("/api/v1/connection-profiles/999/inspector-target-review")
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == ConnectionProfileErrorCode.NOT_FOUND
    finally:
        client.app.dependency_overrides.clear()
